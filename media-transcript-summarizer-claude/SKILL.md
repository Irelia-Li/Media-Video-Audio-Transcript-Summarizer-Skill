---
name: media-transcript-summarizer
description: Extract spoken text from uploaded audio/video files or online video links, generate timestamped transcripts, split long media into chunks, and create overall plus per-chunk summaries. Use when Claude Code is asked to download/fetch a video or audio URL, transcribe podcasts, meetings, interviews, lectures, calls, livestream recordings, Bilibili/YouTube links, MP3/MP4/M4A/WAV/WebM media, create SRT/Markdown/JSON/CSV transcript deliverables, summarize sections, or prepare editorial summaries for reviews, unboxing, card-opening, product guide, meeting, interview, or lecture content.
---

# Media Transcript Summarizer

## Overview

Use this skill in Claude Code to turn a local audio/video file or an online video/audio link into timestamped transcript files and summaries. The bundled script handles URL download, media preparation, transcription, chunk splitting, summary drafts, subtitles, and structured exports.

This skill extracts spoken words from the media audio track. If the user needs on-screen text from video frames, handle OCR separately and merge that text into the final report.

## Install For Claude Code

Place this folder at:

```bash
~/.claude/skills/media-transcript-summarizer
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills"
Copy-Item -Recurse ".\media-transcript-summarizer" "$env:USERPROFILE\.claude\skills\"
```

Install useful dependencies:

```bash
pip install yt-dlp faster-whisper
```

Recommended for video files and long media:

```bash
# Install FFmpeg and make sure ffmpeg / ffprobe are available on PATH.
```

Optional OpenAI mode:

```bash
export OPENAI_API_KEY="YOUR_KEY"
```

PowerShell:

```powershell
$env:OPENAI_API_KEY="YOUR_KEY"
```

## Quick Start

Prefer the bundled script:

```bash
python scripts/transcribe_media.py path/to/media.mp4 --engine local --language zh
python scripts/transcribe_media.py "https://example.com/video.mp4" --download-tool direct --engine local --language zh
python scripts/transcribe_media.py "https://www.bilibili.com/video/BVxxxx/" --download-tool yt-dlp --engine local --language zh
```

Use OpenAI mode when the user wants higher quality:

```bash
python scripts/transcribe_media.py interview.wav --engine openai --language zh --transcribe-model gpt-4o-transcribe --summary-language zh
python scripts/transcribe_media.py panel.mp4 --engine openai --diarize --transcribe-model gpt-4o-transcribe-diarize
python scripts/transcribe_media.py lecture.m4a --engine openai --transcribe-model whisper-1 --timestamps segment
```

## Workflow

1. Confirm whether the user needs transcript only, transcript plus summaries, speaker labels, subtitles, or a specific export format.
2. For private or sensitive media, ask before sending content to a remote API. Use `--engine local` when the user wants local processing.
3. For URLs, verify the user is allowed to access/download the content. Use `--cookies` or `--cookies-from-browser` only for authorized private content.
4. Run `scripts/transcribe_media.py` with an explicit `--out-dir` near the source media or in the current workspace.
5. Inspect `transcript.md` for transcript quality, timestamps, and chunk boundaries.
6. Inspect `summary.md`. If the local summary is repetitive, keyword-like, or misses the point, read the transcript and rewrite `summary.md` into a human editorial summary.
7. Use `transcript.json` for downstream automation, `transcript.csv` for spreadsheet review, and `subtitles.srt` for subtitles.
8. If quality is poor, rerun with a language hint, glossary prompt, shorter chunks, larger local model, or OpenAI mode.

## Engine Selection

- Use `--engine local --local-model base --language zh` for no-API-key local Chinese transcription.
- Use `--engine local --local-model small` or larger when audio is noisy or domain-specific and runtime is acceptable.
- Use `--engine openai --transcribe-model gpt-4o-transcribe` when accuracy matters more than cost.
- Use `--engine openai --transcribe-model gpt-4o-transcribe-diarize --diarize` for speaker-labeled transcripts.
- Use `--engine openai --transcribe-model whisper-1 --timestamps segment` when segment timestamp support is more important than newer model quality.

The OpenAI transcription upload limit is 25 MB per request, so keep chunks under that limit. The script checks chunk sizes before upload.

## Output Files

The script writes:

- `summary.md`: standalone overall summary, highlights, and chunk summaries.
- `transcript.md`: human-readable report with metadata, summaries, and timestamped transcript text.
- `transcript.txt`: plain full transcript.
- `transcript.json`: structured source metadata, overall summary, chunk records, segment records, summaries, and raw responses.
- `transcript.csv`: chunk-level table for spreadsheet review.
- `subtitles.srt`: subtitle file when segments have usable timestamps.

For URL inputs, `transcript.json` records the original URL, downloaded file path, and download method.

## Editorial Summary Rules

Do not deliver raw local extractive summaries when they read like repeated keywords or filler phrases. Treat local summaries as rough drafts and rewrite them from the transcript.

For unboxing, card-opening, product review, shopping guide, or merchandise videos, use this structure:

- One-sentence summary
- Main content
- Highlights
- Notable products or moments
- Segment-by-segment summary with timestamps
- Overall judgment or buyer takeaway

For meetings or interviews, use:

- Agenda/topics
- Decisions
- Action items
- Risks
- Follow-ups

For lectures or tutorials, use:

- Core thesis
- Concepts explained
- Step-by-step flow
- Examples
- Takeaways

## Quality Tips

- Provide `--language zh`, `--language en`, or another ISO-639-1 code when the language is known.
- Use `--download-tool direct` for direct MP4/MP3/WAV URLs and `--download-tool yt-dlp` for platform pages.
- Add `--prompt "Names: ...; terms: ..."` for people, brands, games, technical terms, or mixed-language content when using OpenAI mode.
- Shorten `--chunk-minutes` for noisy media, music-heavy audio, overlapping speakers, or upload-size issues.
- For Bilibili, `--download-format 30280` or another audio-only format often works well.
- Keep chunk boundaries visible in the final report so summaries remain traceable to the source.

## References

Read `references/model-and-dependency-notes.md` when choosing models, troubleshooting URL downloads, explaining upload limits, or installing dependencies.
