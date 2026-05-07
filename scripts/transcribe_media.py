#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import csv
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_API_BASE = "https://api.openai.com/v1"
DEFAULT_TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"
DEFAULT_SUMMARY_MODEL = "gpt-4o-mini"
SUPPORTED_DIRECT_SUFFIXES = {
    ".flac",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".m4a",
    ".ogg",
    ".wav",
    ".webm",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download or read audio/video, transcribe it, and summarize each transcript chunk."
    )
    parser.add_argument("media", help="Input audio/video file path or HTTP(S) media/video URL.")
    parser.add_argument("--out-dir", type=Path, help="Output directory.")
    parser.add_argument("--api-base", default=os.getenv("OPENAI_BASE_URL", DEFAULT_API_BASE))
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument(
        "--engine",
        choices=["openai", "local"],
        default="openai",
        help="Transcription engine. local uses faster-whisper and does not require an OpenAI API key.",
    )
    parser.add_argument("--transcribe-model", default=os.getenv("OPENAI_TRANSCRIBE_MODEL", DEFAULT_TRANSCRIBE_MODEL))
    parser.add_argument("--summary-model", default=os.getenv("OPENAI_SUMMARY_MODEL", DEFAULT_SUMMARY_MODEL))
    parser.add_argument("--local-model", default="small", help="faster-whisper model size/name for --engine local.")
    parser.add_argument("--local-device", default="cpu", help="faster-whisper device, for example cpu or cuda.")
    parser.add_argument("--local-compute-type", default="int8", help="faster-whisper compute type.")
    parser.add_argument("--local-cpu-threads", type=int, default=4, help="CPU threads for local transcription.")
    parser.add_argument(
        "--download-tool",
        choices=["auto", "yt-dlp", "direct"],
        default="auto",
        help="How to fetch URL inputs. auto tries yt-dlp, then direct HTTP.",
    )
    parser.add_argument(
        "--download-format",
        default="bestaudio/best",
        help="yt-dlp format selector for URL inputs.",
    )
    parser.add_argument("--cookies", type=Path, help="Cookies file for yt-dlp URL downloads.")
    parser.add_argument(
        "--cookies-from-browser",
        help="Browser name for yt-dlp cookies, for example chrome, edge, or firefox.",
    )
    parser.add_argument("--language", help="Optional ISO-639-1 language hint, for example zh or en.")
    parser.add_argument("--prompt", help="Optional glossary/context prompt for transcription.")
    parser.add_argument("--chunk-minutes", type=float, default=10.0, help="Chunk duration before upload.")
    parser.add_argument("--max-upload-mb", type=float, default=24.0, help="Maximum chunk size before upload.")
    parser.add_argument("--bitrate", default="64k", help="Audio bitrate for generated chunks.")
    parser.add_argument("--summary-language", default="same", help="Summary language: same, zh, en, etc.")
    parser.add_argument("--no-summary", action="store_true", help="Skip chunk and overall summaries.")
    parser.add_argument("--diarize", action="store_true", help="Request diarized speaker-labeled output.")
    parser.add_argument(
        "--timestamps",
        choices=["none", "segment", "word"],
        default="none",
        help="Request verbose timestamps. Use with whisper-1.",
    )
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary chunks.")
    parser.add_argument("--dry-run", action="store_true", help="Prepare and print the plan without API calls.")
    parser.add_argument("--timeout", type=int, default=600, help="HTTP timeout in seconds.")
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def run(cmd: list[str]) -> str:
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(details or f"Command failed: {' '.join(cmd)}")
    return completed.stdout.strip()


def is_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def safe_slug(value: str, fallback: str = "linked_media") -> str:
    value = urllib.parse.unquote(value).strip().lower()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = value.strip(".-_")
    return (value[:80] or fallback).strip(".-_") or fallback


def default_output_dir(media_arg: str) -> Path:
    if is_url(media_arg):
        parsed = urllib.parse.urlparse(media_arg)
        slug_source = f"{parsed.netloc}{parsed.path}" or "linked_media"
        return Path.cwd() / f"{safe_slug(slug_source)}_transcript"
    media = Path(media_arg)
    return media.with_name(f"{media.stem}_transcript")


def yt_dlp_command() -> list[str] | None:
    executable = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if executable:
        return [executable]
    probe = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--version"],
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        return [sys.executable, "-m", "yt_dlp"]
    return None


def download_with_ytdlp(args: argparse.Namespace, download_dir: Path) -> Path:
    command = yt_dlp_command()
    if not command:
        raise RuntimeError("yt-dlp is not installed.")

    before = {path.resolve() for path in download_dir.glob("*") if path.is_file()}
    output_template = str(download_dir / "%(title).200B [%(id)s].%(ext)s")
    cmd = [*command]
    if args.cookies:
        cmd.extend(["--cookies", str(args.cookies)])
    if args.cookies_from_browser:
        cmd.extend(["--cookies-from-browser", args.cookies_from_browser])
    cmd.extend(
        [
            "--no-playlist",
            "-f",
            args.download_format,
            "-o",
            output_template,
            args.media,
        ]
    )
    run(cmd)

    after = [
        path
        for path in download_dir.glob("*")
        if path.is_file()
        and path.resolve() not in before
        and not path.name.endswith((".part", ".ytdl", ".json"))
    ]
    if not after:
        after = [
            path
            for path in download_dir.glob("*")
            if path.is_file() and not path.name.endswith((".part", ".ytdl", ".json"))
        ]
    if not after:
        raise RuntimeError("yt-dlp finished but no media file was found.")
    return max(after, key=lambda path: path.stat().st_mtime)


def filename_from_response(url: str, response: Any) -> str:
    disposition = response.headers.get("Content-Disposition", "")
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', disposition, re.IGNORECASE)
    if match:
        return safe_slug(match.group(1), "downloaded_media")
    final_url = response.geturl() if hasattr(response, "geturl") else url
    parsed = urllib.parse.urlparse(final_url or url)
    name = Path(urllib.parse.unquote(parsed.path)).name
    if name:
        return safe_slug(name, "downloaded_media")
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
    extension = mimetypes.guess_extension(content_type) or ".bin"
    return f"downloaded_media{extension}"


def download_direct(args: argparse.Namespace, download_dir: Path) -> Path:
    request = urllib.request.Request(
        args.media,
        headers={"User-Agent": "Mozilla/5.0 (Codex media transcript downloader)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            filename = filename_from_response(args.media, response)
            target = download_dir / filename
            counter = 1
            while target.exists():
                target = download_dir / f"{Path(filename).stem}-{counter}{Path(filename).suffix}"
                counter += 1
            with target.open("wb") as handle:
                shutil.copyfileobj(response, handle)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Direct download failed: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Direct download failed: {exc}") from exc
    return target


def resolve_media_source(args: argparse.Namespace, work_dir: Path) -> tuple[Path, dict[str, Any]]:
    source = str(args.media)
    if not is_url(source):
        media = Path(source)
        if not media.exists():
            fail(f"Input file not found: {media}")
        resolved = media.resolve()
        return resolved, {"input_type": "file", "path": str(resolved)}

    download_dir = work_dir / "download"
    download_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    downloaded: Path | None = None
    method = args.download_tool

    if method in {"auto", "yt-dlp"}:
        try:
            print("Downloading URL with yt-dlp...")
            downloaded = download_with_ytdlp(args, download_dir)
            method = "yt-dlp"
        except Exception as exc:
            if args.download_tool == "yt-dlp":
                fail(f"yt-dlp download failed: {exc}")
            errors.append(str(exc))

    if downloaded is None and args.download_tool in {"auto", "direct"}:
        try:
            print("Downloading URL directly...")
            downloaded = download_direct(args, download_dir)
            method = "direct"
        except Exception as exc:
            errors.append(str(exc))

    if downloaded is None:
        fail("Could not download URL. " + " | ".join(errors))

    return downloaded.resolve(), {
        "input_type": "url",
        "url": source,
        "download_method": method,
        "path": str(downloaded.resolve()),
    }


def ffprobe_duration(ffprobe: str, media: Path) -> float | None:
    try:
        out = run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(media),
            ]
        )
        return float(out)
    except Exception:
        return None


def make_chunks(args: argparse.Namespace, work_dir: Path) -> list[dict[str, Any]]:
    media = args.media.resolve()
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    max_bytes = int(args.max_upload_mb * 1024 * 1024)

    if ffmpeg and ffprobe:
        duration = ffprobe_duration(ffprobe, media)
        if not duration:
            duration = args.chunk_minutes * 60
        chunk_seconds = max(30, int(args.chunk_minutes * 60))
        chunks_dir = work_dir / "chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)
        chunks: list[dict[str, Any]] = []
        start = 0.0
        index = 1
        while start < duration + 0.01:
            end = min(start + chunk_seconds, duration)
            if end <= start:
                break
            chunk_path = chunks_dir / f"chunk_{index:04d}.mp3"
            cmd = [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{end - start:.3f}",
                "-i",
                str(media),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-b:a",
                args.bitrate,
                str(chunk_path),
            ]
            run(cmd)
            size = chunk_path.stat().st_size
            if size > max_bytes:
                fail(
                    f"{chunk_path.name} is {size / 1024 / 1024:.1f} MB. "
                    f"Reduce --chunk-minutes or --bitrate below the {args.max_upload_mb:.1f} MB limit."
                )
            chunks.append(
                {
                    "index": index,
                    "path": chunk_path,
                    "start": start,
                    "end": end,
                    "duration": end - start,
                    "size_bytes": size,
                }
            )
            index += 1
            start += chunk_seconds
        if not chunks:
            fail("No audio chunks were created. Check that the media file contains an audio stream.")
        return chunks

    size = media.stat().st_size
    if args.engine == "local":
        return [
            {
                "index": 1,
                "path": media,
                "start": 0.0,
                "end": None,
                "duration": None,
                "size_bytes": size,
            }
        ]
    if media.suffix.lower() not in SUPPORTED_DIRECT_SUFFIXES:
        fail("ffmpeg/ffprobe are required for this file type. Install FFmpeg and rerun.")
    if size > max_bytes:
        fail("ffmpeg/ffprobe are required to split this file before upload.")
    return [
        {
            "index": 1,
            "path": media,
            "start": 0.0,
            "end": None,
            "duration": None,
            "size_bytes": size,
        }
    ]


def api_key(args: argparse.Namespace) -> str:
    key = os.getenv(args.api_key_env)
    if not key:
        fail(f"Set {args.api_key_env} before running transcription.")
    return key


def multipart_post(
    url: str,
    key: str,
    fields: dict[str, Any],
    file_field: tuple[str, Path],
    timeout: int,
) -> Any:
    boundary = f"----codex-{uuid.uuid4().hex}"
    body = bytearray()

    def add_field(name: str, value: Any) -> None:
        values = value if isinstance(value, list) else [value]
        for item in values:
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            body.extend(str(item).encode("utf-8"))
            body.extend(b"\r\n")

    for field_name, field_value in fields.items():
        if field_value is not None:
            add_field(field_name, field_value)

    name, path = file_field
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        (
            f'Content-Disposition: form-data; name="{name}"; '
            f'filename="{path.name}"\r\nContent-Type: {mime_type}\r\n\r\n'
        ).encode()
    )
    body.extend(path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    request = urllib.request.Request(
        url,
        data=bytes(body),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    return openai_request(request, timeout)


def json_post(url: str, key: str, payload: dict[str, Any], timeout: int) -> Any:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    return openai_request(request, timeout)


def openai_request(request: urllib.request.Request, timeout: int) -> Any:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API request failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc}") from exc

    text = raw.decode("utf-8", errors="replace")
    if "application/json" in content_type or text.lstrip().startswith("{"):
        return json.loads(text)
    return text


def transcribe_chunk(args: argparse.Namespace, key: str, chunk: dict[str, Any]) -> dict[str, Any]:
    model = args.transcribe_model
    fields: dict[str, Any] = {"model": model}
    is_diarize = args.diarize or "diarize" in model

    if is_diarize:
        fields["response_format"] = "diarized_json"
        fields["chunking_strategy"] = "auto"
    elif model == "whisper-1" and args.timestamps != "none":
        fields["response_format"] = "verbose_json"
        fields["timestamp_granularities[]"] = args.timestamps
    else:
        fields["response_format"] = "json"

    if args.language:
        fields["language"] = args.language
    if args.prompt and not is_diarize:
        fields["prompt"] = args.prompt

    url = f"{args.api_base.rstrip('/')}/audio/transcriptions"
    response = multipart_post(url, key, fields, ("file", chunk["path"]), args.timeout)
    if isinstance(response, str):
        return {"text": response}
    return response


def load_local_model(args: argparse.Namespace) -> Any:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        fail("Install faster-whisper for --engine local: python -m pip install faster-whisper")
    return WhisperModel(
        args.local_model,
        device=args.local_device,
        compute_type=args.local_compute_type,
        cpu_threads=args.local_cpu_threads,
    )


def transcribe_chunk_local(args: argparse.Namespace, model: Any, chunk: dict[str, Any]) -> dict[str, Any]:
    segments_iter, info = model.transcribe(
        str(chunk["path"]),
        language=args.language,
        task="transcribe",
        beam_size=5,
        vad_filter=True,
        word_timestamps=args.timestamps == "word",
    )
    segments: list[dict[str, Any]] = []
    text_parts: list[str] = []
    offset = float(chunk.get("start") or 0.0)
    for segment in segments_iter:
        text = segment.text.strip()
        if not text:
            continue
        text_parts.append(text)
        segments.append(
            {
                "start": offset + float(segment.start),
                "end": offset + float(segment.end),
                "text": text,
            }
        )
    return {
        "text": "\n".join(text_parts),
        "segments": segments,
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
    }


def extract_response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if not isinstance(response, dict):
        return ""
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    parts: list[str] = []
    for item in response.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def summarize_chunk(args: argparse.Namespace, key: str, chunk_text: str) -> dict[str, Any]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "key_points": {"type": "array", "items": {"type": "string"}},
            "action_items": {"type": "array", "items": {"type": "string"}},
            "notable_terms": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "key_points", "action_items", "notable_terms"],
    }
    language_instruction = (
        "Use the same language as the transcript."
        if args.summary_language == "same"
        else f"Write the summary in {args.summary_language}."
    )
    payload = {
        "model": args.summary_model,
        "instructions": (
            "Summarize one transcript chunk faithfully. "
            "Do not add facts that are not in the transcript. "
            f"{language_instruction}"
        ),
        "input": (
            "Return a concise structured summary for this transcript chunk.\n\n"
            f"{chunk_text}"
        ),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "chunk_summary",
                "schema": schema,
                "strict": True,
            }
        },
        "max_output_tokens": 900,
    }
    response = json_post(f"{args.api_base.rstrip('/')}/responses", key, payload, args.timeout)
    output_text = extract_response_text(response)
    try:
        parsed = json.loads(output_text)
        parsed["_raw_response_id"] = response.get("id") if isinstance(response, dict) else None
        return parsed
    except json.JSONDecodeError:
        return {
            "summary": output_text,
            "key_points": [],
            "action_items": [],
            "notable_terms": [],
            "_raw_response": response,
        }


def summarize_overall_openai(args: argparse.Namespace, key: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "topics": {"type": "array", "items": {"type": "string"}},
            "key_points": {"type": "array", "items": {"type": "string"}},
            "timeline": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "time": {"type": "string"},
                        "point": {"type": "string"},
                    },
                    "required": ["time", "point"],
                },
            },
        },
        "required": ["summary", "topics", "key_points", "timeline"],
    }
    language_instruction = (
        "Use the same language as the transcript."
        if args.summary_language == "same"
        else f"Write the summary in {args.summary_language}."
    )
    chunk_blocks = []
    for chunk in chunks:
        chunk_blocks.append(
            f"Chunk {chunk['index']:04d} [{fmt_time(chunk.get('start'))} - {fmt_time(chunk.get('end'))}]\n"
            f"{chunk.get('text', '')}"
        )
    payload = {
        "model": args.summary_model,
        "instructions": (
            "Create a faithful overall summary for the full transcript. "
            "Do not add facts that are not in the transcript. "
            f"{language_instruction}"
        ),
        "input": "\n\n".join(chunk_blocks),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "overall_summary",
                "schema": schema,
                "strict": True,
            }
        },
        "max_output_tokens": 1200,
    }
    response = json_post(f"{args.api_base.rstrip('/')}/responses", key, payload, args.timeout)
    output_text = extract_response_text(response)
    try:
        parsed = json.loads(output_text)
        parsed["_raw_response_id"] = response.get("id") if isinstance(response, dict) else None
        return parsed
    except json.JSONDecodeError:
        return {
            "summary": output_text,
            "topics": [],
            "key_points": [],
            "timeline": [],
            "_raw_response": response,
        }


COMMON_SUMMARY_WORDS = {
    "我们",
    "你们",
    "他们",
    "这个",
    "那个",
    "可以",
    "就是",
    "一下",
    "现在",
    "这里",
    "那里",
    "然后",
    "没有",
    "不用",
    "还是",
    "已经",
    "really",
    "there",
    "their",
    "about",
    "would",
    "could",
    "should",
    "this",
    "that",
    "with",
    "from",
    "have",
    "were",
}


ACTION_CUES = (
    "看",
    "打",
    "走",
    "来",
    "开",
    "追",
    "等",
    "抢",
    "拿",
    "推",
    "杀",
    "拉",
    "保",
    "转",
    "撤",
    "控",
    "慢",
    "快",
    "go",
    "push",
    "fight",
    "wait",
)


def looks_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def split_summary_units(text: str) -> list[str]:
    units: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        parts = re.split(r"(?<=[。！？!?；;])\s*|[。！？!?；;]", line)
        for part in parts:
            part = part.strip(" ,，、")
            if 3 <= len(part) <= 120:
                units.append(part)
    return units


def summary_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    tokens.extend(match.group(0).lower() for match in re.finditer(r"[A-Za-z][A-Za-z0-9_-]{1,}", text))
    chinese = re.sub(r"[^\u4e00-\u9fff]", "", text)
    for size in (2, 3):
        for index in range(0, max(0, len(chinese) - size + 1)):
            token = chinese[index : index + size]
            if token not in COMMON_SUMMARY_WORDS:
                tokens.append(token)
    return [token for token in tokens if token not in COMMON_SUMMARY_WORDS]


def pick_representative_units(text: str, limit: int = 5) -> list[str]:
    units = split_summary_units(text)
    if not units:
        return []
    frequencies = Counter(token for unit in units for token in summary_tokens(unit))
    if not frequencies:
        return units[:limit]

    scored: list[tuple[float, int, str]] = []
    total = len(units)
    for index, unit in enumerate(units):
        tokens = summary_tokens(unit)
        if not tokens:
            continue
        score = sum(frequencies[token] for token in tokens) / math.sqrt(len(tokens))
        if any(cue.lower() in unit.lower() for cue in ACTION_CUES):
            score += 1.5
        if index < max(2, total // 10) or index > total - max(2, total // 10):
            score += 0.5
        scored.append((score, index, unit))
    selected = sorted(scored, key=lambda item: (-item[0], item[1]))[:limit]
    return [unit for _, _, unit in sorted(selected, key=lambda item: item[1])]


def notable_terms(text: str, limit: int = 10) -> list[str]:
    counts = Counter(summary_tokens(text))
    terms: list[str] = []
    for token, _ in counts.most_common(limit * 3):
        if token in COMMON_SUMMARY_WORDS:
            continue
        if len(token) < 2:
            continue
        if token not in terms:
            terms.append(token)
        if len(terms) >= limit:
            break
    return terms


def action_lines(text: str, limit: int = 6) -> list[str]:
    lines = split_summary_units(text)
    picked = []
    for line in lines:
        if any(cue.lower() in line.lower() for cue in ACTION_CUES):
            picked.append(line)
        if len(picked) >= limit:
            break
    return picked


def summarize_text_local(text: str, language: str | None = None, limit: int = 5) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {"summary": "", "key_points": [], "action_items": [], "notable_terms": [], "method": "local_extractive"}
    key_points = pick_representative_units(text, limit=limit)
    terms = notable_terms(text)
    actions = action_lines(text)
    zh = (language or "").startswith("zh") or looks_chinese(text)
    if key_points:
        if zh:
            summary = "本地抽取式总结：本段代表性内容包括：" + "；".join(key_points[:3]) + "。"
        else:
            summary = "Local extractive summary: representative points include " + "; ".join(key_points[:3]) + "."
    else:
        summary = text[:240]
    return {
        "summary": summary,
        "key_points": key_points,
        "action_items": actions,
        "notable_terms": terms,
        "method": "local_extractive",
    }


def summarize_overall_local(chunks: list[dict[str, Any]], language: str | None = None) -> dict[str, Any]:
    full_text = "\n".join(chunk.get("text", "") for chunk in chunks if chunk.get("text"))
    summary = summarize_text_local(full_text, language=language, limit=8)
    timeline = []
    for chunk in chunks:
        chunk_summary = chunk.get("summary") or {}
        point = chunk_summary.get("summary") or (chunk.get("text", "").strip()[:120])
        if point:
            timeline.append({"time": fmt_time(chunk.get("start")), "point": point})
    return {
        "summary": summary["summary"],
        "topics": summary["notable_terms"][:8],
        "key_points": summary["key_points"],
        "timeline": timeline[:12],
        "method": "local_extractive",
    }


def split_local_transcription_chunk(
    args: argparse.Namespace,
    source_chunk: dict[str, Any],
    raw: dict[str, Any],
    normalized_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not normalized_segments:
        return [
            {
                "index": source_chunk["index"],
                "start": source_chunk.get("start"),
                "end": source_chunk.get("end"),
                "duration": source_chunk.get("duration"),
                "size_bytes": source_chunk.get("size_bytes"),
                "text": (raw.get("text") or "").strip(),
                "segments": [],
                "summary": None,
                "raw_transcription": raw,
            }
        ]

    chunk_seconds = max(30, int(args.chunk_minutes * 60))
    min_start = float(source_chunk.get("start") or 0.0)
    max_end = max(float(segment.get("end") or segment.get("start") or 0.0) for segment in normalized_segments)
    if source_chunk.get("end") is not None:
        max_end = max(max_end, float(source_chunk["end"]))

    result_chunks: list[dict[str, Any]] = []
    current_start = min_start
    index = 1
    while current_start < max_end + 0.01:
        current_end = min(current_start + chunk_seconds, max_end)
        segment_group = [
            segment
            for segment in normalized_segments
            if current_start <= float(segment.get("start") or 0.0) < current_end
        ]
        if segment_group:
            text = "\n".join(segment.get("text", "").strip() for segment in segment_group if segment.get("text"))
            summary = summarize_text_local(text, language=args.language) if text and not args.no_summary else None
            result_chunks.append(
                {
                    "index": index,
                    "start": current_start,
                    "end": current_end,
                    "duration": current_end - current_start,
                    "size_bytes": source_chunk.get("size_bytes") if index == 1 else None,
                    "text": text,
                    "segments": [
                        {
                            **segment,
                            "id": f"{index:04d}-{segment_number:04d}",
                            "chunk_index": index,
                        }
                        for segment_number, segment in enumerate(segment_group, 1)
                    ],
                    "summary": summary,
                    "raw_transcription": raw if index == 1 else {},
                }
            )
            index += 1
        current_start += chunk_seconds
    return result_chunks


def normalize_segments(response: dict[str, Any], chunk: dict[str, Any]) -> list[dict[str, Any]]:
    start_offset = float(chunk["start"] or 0.0)
    chunk_end = chunk.get("end")
    text = (response.get("text") or "").strip()
    raw_segments = response.get("segments") or []
    segments: list[dict[str, Any]] = []

    for idx, segment in enumerate(raw_segments, start=1):
        segment_text = (segment.get("text") or "").strip()
        if not segment_text:
            continue
        raw_start = float(segment.get("start", 0.0) or 0.0)
        start = raw_start if raw_start >= start_offset else start_offset + raw_start
        end_value = segment.get("end")
        if end_value is None:
            end = None
        else:
            raw_end = float(end_value)
            end = raw_end if raw_end >= start_offset else start_offset + raw_end
        segments.append(
            {
                "id": f"{chunk['index']:04d}-{idx:04d}",
                "chunk_index": chunk["index"],
                "start": start,
                "end": end,
                "speaker": segment.get("speaker"),
                "text": segment_text,
            }
        )

    if not segments and text:
        segments.append(
            {
                "id": f"{chunk['index']:04d}-0001",
                "chunk_index": chunk["index"],
                "start": start_offset,
                "end": chunk_end,
                "speaker": None,
                "text": text,
            }
        )
    return segments


def fmt_time(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    seconds = max(0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def fmt_srt_time(seconds: float | None) -> str:
    if seconds is None:
        seconds = 0.0
    seconds = max(0, float(seconds))
    millis = int(round((seconds - int(seconds)) * 1000))
    whole = int(seconds)
    hours = whole // 3600
    minutes = (whole % 3600) // 60
    secs = whole % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_outputs(out_dir: Path, result: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks = result["chunks"]

    (out_dir / "transcript.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "transcript.txt").write_text(
        "\n\n".join(chunk["text"].strip() for chunk in chunks if chunk["text"].strip()),
        encoding="utf-8",
    )

    with (out_dir / "transcript.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["chunk", "start", "end", "duration_seconds", "summary", "text"],
        )
        writer.writeheader()
        for chunk in chunks:
            summary = chunk.get("summary") or {}
            writer.writerow(
                {
                    "chunk": chunk["index"],
                    "start": fmt_time(chunk.get("start")),
                    "end": fmt_time(chunk.get("end")),
                    "duration_seconds": chunk.get("duration"),
                    "summary": summary.get("summary", ""),
                    "text": chunk.get("text", ""),
                }
            )

    markdown = render_markdown(result)
    (out_dir / "transcript.md").write_text(markdown, encoding="utf-8")
    summary_markdown = render_summary_markdown(result)
    if summary_markdown.strip():
        (out_dir / "summary.md").write_text(summary_markdown, encoding="utf-8")

    srt = render_srt(result)
    if srt.strip():
        (out_dir / "subtitles.srt").write_text(srt, encoding="utf-8")


def render_summary_markdown(result: dict[str, Any]) -> str:
    overall = result.get("summary")
    chunks = result.get("chunks", [])
    if not overall and not any(chunk.get("summary") for chunk in chunks):
        return ""
    lines = [
        f"# Summary: {result['source']['name']}",
        "",
        f"- Generated: {result['generated_at']}",
        f"- Transcription model: {result['models']['transcribe']}",
        f"- Summary model: {result['models']['summary'] or 'none'}",
        "",
    ]
    if overall:
        lines.extend(["## Overall", ""])
        if overall.get("summary"):
            lines.extend([overall["summary"].strip(), ""])
        if overall.get("topics"):
            lines.extend(["### Topics", ""])
            lines.extend(f"- {topic}" for topic in overall["topics"])
            lines.append("")
        if overall.get("key_points"):
            lines.extend(["### Key Points", ""])
            lines.extend(f"- {point}" for point in overall["key_points"])
            lines.append("")
        if overall.get("timeline"):
            lines.extend(["### Timeline", ""])
            for item in overall["timeline"]:
                lines.append(f"- [{item.get('time', 'unknown')}] {item.get('point', '').strip()}")
            lines.append("")
    chunk_summaries = [chunk for chunk in chunks if chunk.get("summary")]
    if chunk_summaries:
        lines.extend(["## Chunk Summaries", ""])
        for chunk in chunk_summaries:
            summary = chunk.get("summary") or {}
            lines.append(f"### Chunk {chunk['index']:04d} [{fmt_time(chunk.get('start'))} - {fmt_time(chunk.get('end'))}]")
            lines.append("")
            if summary.get("summary"):
                lines.extend([summary["summary"].strip(), ""])
            if summary.get("key_points"):
                lines.extend(f"- {point}" for point in summary["key_points"])
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# Transcript: {result['source']['name']}",
        "",
        f"- Generated: {result['generated_at']}",
        f"- Transcription model: {result['models']['transcribe']}",
        f"- Summary model: {result['models']['summary'] or 'none'}",
        f"- Chunks: {len(result['chunks'])}",
        "",
    ]
    overall = result.get("summary")
    if overall:
        lines.extend(["## Overall Summary", ""])
        if overall.get("summary"):
            lines.extend([overall["summary"].strip(), ""])
        if overall.get("topics"):
            lines.extend(["### Topics", ""])
            lines.extend(f"- {topic}" for topic in overall["topics"])
            lines.append("")
        if overall.get("key_points"):
            lines.extend(["### Key Points", ""])
            lines.extend(f"- {point}" for point in overall["key_points"])
            lines.append("")
        if overall.get("timeline"):
            lines.extend(["### Timeline", ""])
            for item in overall["timeline"]:
                lines.append(f"- [{item.get('time', 'unknown')}] {item.get('point', '').strip()}")
            lines.append("")
    for chunk in result["chunks"]:
        lines.extend(
            [
                f"## Chunk {chunk['index']:04d} [{fmt_time(chunk.get('start'))} - {fmt_time(chunk.get('end'))}]",
                "",
            ]
        )
        summary = chunk.get("summary")
        if summary:
            if summary.get("summary"):
                lines.extend(["### Summary", "", summary["summary"].strip(), ""])
            if summary.get("key_points"):
                lines.extend(["### Key Points", ""])
                lines.extend(f"- {point}" for point in summary["key_points"])
                lines.append("")
            if summary.get("action_items"):
                lines.extend(["### Action Items", ""])
                lines.extend(f"- {item}" for item in summary["action_items"])
                lines.append("")
        lines.extend(["### Transcript", ""])
        for segment in chunk.get("segments", []):
            speaker = f" {segment['speaker']}:" if segment.get("speaker") else ""
            lines.append(
                f"[{fmt_time(segment.get('start'))} - {fmt_time(segment.get('end'))}]{speaker} "
                f"{segment.get('text', '').strip()}"
            )
        if not chunk.get("segments"):
            lines.append(chunk.get("text", "").strip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_srt(result: dict[str, Any]) -> str:
    blocks: list[str] = []
    counter = 1
    for chunk in result["chunks"]:
        for segment in chunk.get("segments", []):
            text = segment.get("text", "").strip()
            start = segment.get("start")
            end = segment.get("end")
            if not text or start is None or end is None or end <= start:
                continue
            speaker = f"{segment['speaker']}: " if segment.get("speaker") else ""
            blocks.append(
                f"{counter}\n{fmt_srt_time(start)} --> {fmt_srt_time(end)}\n{speaker}{text}\n"
            )
            counter += 1
    return "\n".join(blocks)


def main() -> None:
    args = parse_args()
    source_input = str(args.media)
    if args.chunk_minutes <= 0:
        fail("--chunk-minutes must be greater than 0.")
    if args.max_upload_mb <= 0:
        fail("--max-upload-mb must be greater than 0.")
    if args.diarize and "diarize" not in args.transcribe_model:
        args.transcribe_model = "gpt-4o-transcribe-diarize"

    out_dir = args.out_dir or default_output_dir(source_input)
    temp_parent = out_dir / "_temp"
    temp_parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="media-transcript-", dir=temp_parent))

    try:
        media_path, source_details = resolve_media_source(args, work_dir)
        args.media = media_path
        chunks = make_chunks(args, work_dir)
        print(f"Prepared {len(chunks)} chunk(s).")
        for chunk in chunks:
            size_mb = chunk["size_bytes"] / 1024 / 1024
            print(
                f"  chunk {chunk['index']:04d}: {fmt_time(chunk.get('start'))} - "
                f"{fmt_time(chunk.get('end'))}, {size_mb:.2f} MB"
            )

        if args.dry_run:
            print("Dry run complete. No API calls were made.")
            return

        key = api_key(args) if args.engine == "openai" else None
        local_model = load_local_model(args) if args.engine == "local" else None
        result_chunks: list[dict[str, Any]] = []
        for chunk in chunks:
            print(f"Transcribing chunk {chunk['index']:04d}...")
            raw = (
                transcribe_chunk_local(args, local_model, chunk)
                if args.engine == "local"
                else transcribe_chunk(args, key, chunk)
            )
            text = (raw.get("text") or "").strip()
            segments = normalize_segments(raw, chunk)
            if args.engine == "local":
                print(f"Creating local extractive summaries for chunk {chunk['index']:04d}...")
                next_chunks = split_local_transcription_chunk(args, chunk, raw, segments)
                offset = len(result_chunks)
                for local_chunk in next_chunks:
                    local_chunk["index"] = offset + local_chunk["index"]
                    for segment in local_chunk.get("segments", []):
                        old_id = segment.get("id", "0000-0000")
                        suffix = old_id.split("-", 1)[-1]
                        segment["id"] = f"{local_chunk['index']:04d}-{suffix}"
                        segment["chunk_index"] = local_chunk["index"]
                result_chunks.extend(next_chunks)
            else:
                summary = None
                if not args.no_summary and text:
                    print(f"Summarizing chunk {chunk['index']:04d}...")
                    summary = summarize_chunk(args, key, text)
                result_chunks.append(
                    {
                        "index": chunk["index"],
                        "start": chunk.get("start"),
                        "end": chunk.get("end"),
                        "duration": chunk.get("duration"),
                        "size_bytes": chunk.get("size_bytes"),
                        "text": text,
                        "segments": segments,
                        "summary": summary,
                        "raw_transcription": raw,
                    }
                )
            time.sleep(0.2)

        overall_summary = None
        if not args.no_summary and result_chunks:
            if args.engine == "local":
                print("Creating local extractive overall summary...")
                overall_summary = summarize_overall_local(result_chunks, language=args.language)
            else:
                print("Creating overall summary...")
                overall_summary = summarize_overall_openai(args, key, result_chunks)

        result = {
            "source": {
                "input": source_input,
                **source_details,
                "name": media_path.name,
                "size_bytes": media_path.stat().st_size,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "models": {
                "transcribe": args.transcribe_model if args.engine == "openai" else f"local:{args.local_model}",
                "summary": (
                    args.summary_model
                    if args.engine == "openai" and not args.no_summary
                    else ("local_extractive" if args.engine == "local" and not args.no_summary else None)
                ),
            },
            "options": {
                "engine": args.engine,
                "language": args.language,
                "chunk_minutes": args.chunk_minutes,
                "summary_language": args.summary_language,
                "diarize": args.diarize,
                "timestamps": args.timestamps,
            },
            "summary": overall_summary,
            "chunks": result_chunks,
        }
        write_outputs(out_dir, result)
        print(f"Done. Wrote transcript files to: {out_dir.resolve()}")
    finally:
        if args.keep_temp:
            print(f"Kept temporary files at: {work_dir}")
        else:
            shutil.rmtree(work_dir, ignore_errors=True)
            try:
                temp_parent.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    main()
