---
name: media-transcript-summarizer
description: Extract spoken text from audio/video files or video links, generate timestamped verbatim transcripts, and summarize each transcript chunk. Use when Codex is asked to download or fetch a video/audio URL, transcribe podcasts, meetings, interviews, lectures, calls, livestream recordings, MP3/MP4/M4A/WAV/WebM media, create SRT/Markdown/JSON transcript deliverables, split long media into chunks, summarize each section, or optionally produce speaker-labeled transcripts with diarization.
---

# Media Transcript Summarizer

## Overview

Use this skill to turn a local audio/video file or a video/audio link into a timestamped transcript plus per-chunk summaries. The bundled script handles URL download, media preparation, chunking, OpenAI speech-to-text requests, chunk summaries, and export files.

This skill is for spoken words. If the user also needs on-screen text from video frames, extract subtitles/OCR separately and merge that text into the final report.

## Quick Start

Prefer the bundled script:

```bash
python scripts/transcribe_media.py path/to/media.mp4 --out-dir output/transcript
python scripts/transcribe_media.py "https://example.com/video.mp4" --out-dir output/transcript
```

Common options:

```bash
python scripts/transcribe_media.py meeting.mp4 --language zh --chunk-minutes 8
python scripts/transcribe_media.py "https://www.youtube.com/watch?v=..." --download-tool yt-dlp --language en
python scripts/transcribe_media.py audio.m4a --engine local --language zh
python scripts/transcribe_media.py interview.wav --transcribe-model gpt-4o-transcribe --summary-language zh
python scripts/transcribe_media.py panel.mp4 --diarize --transcribe-model gpt-4o-transcribe-diarize
python scripts/transcribe_media.py lecture.m4a --transcribe-model whisper-1 --timestamps segment
```

Requirements:

- Set `OPENAI_API_KEY` before calling the script when using the default OpenAI engine.
- Install `faster-whisper` for offline/local transcription with `--engine local`; this mode does not require an OpenAI API key and produces extractive summaries.
- Install `ffmpeg` and `ffprobe` for video files or long audio files that must be split.
- Install `yt-dlp` for platform links such as YouTube, Bilibili, Vimeo, X/Twitter, or pages that are not direct MP4/MP3 file URLs.
- For a single small supported audio file, the script can upload directly even when `ffmpeg` is unavailable.

## Workflow

1. Confirm the user's goal: transcript only, transcript plus chunk summaries, speaker labels, subtitles, or a specific output format.
2. Check whether the media is sensitive. Ask before sending private, regulated, or confidential media to a remote API.
3. For URLs, verify the user is allowed to access/download the content and use `--cookies` or `--cookies-from-browser` only for authorized private content.
4. Run `scripts/transcribe_media.py` with an output directory near the source media or in the current workspace.
5. Inspect `transcript.md` first for readability, timestamps, and chunk summaries.
6. Rewrite `summary.md` into a human editorial summary when local extractive summaries are too literal, repetitive, or keyword-like.
7. Use `transcript.json` for downstream automation, `transcript.csv` for spreadsheets, and `subtitles.srt` when subtitles are needed.
8. If the transcript quality is poor, rerun with a language hint, glossary prompt, shorter chunks, or a higher-quality transcription model.

## Model Selection

OpenAI's transcription endpoint supports `gpt-4o-mini-transcribe`, `gpt-4o-transcribe`, `gpt-4o-transcribe-diarize`, and `whisper-1`.

- Use `gpt-4o-mini-transcribe` by default for cost-effective transcription.
- Use `gpt-4o-transcribe` when accuracy matters more than cost.
- Use `gpt-4o-transcribe-diarize` with `--diarize` for speaker labels.
- Use `whisper-1 --timestamps segment` when segment-level timestamp output is more important than using the newer transcription models.
- Use `--engine local --local-model small --language zh` when the user wants direct local recognition and an extractive summary without an API key.

The OpenAI transcription upload limit is 25 MB per request, so keep chunks under that limit. The script defaults to compressed mono MP3 chunks and checks chunk sizes before uploading.

## Output Contract

The script writes:

- `transcript.md`: human-readable report with metadata, chunk summaries, and transcript text.
- `summary.md`: standalone overall summary and chunk summaries.
- `transcript.txt`: plain full transcript.
- `transcript.json`: structured media metadata, overall summary, chunk records, segment records, chunk summaries, and raw API responses.
- `transcript.csv`: chunk-level table for spreadsheet review.
- `subtitles.srt`: subtitle file when segments have usable timestamps.

For URL inputs, `transcript.json` records the original URL, local downloaded file path, and download method.

## Editorial Summary

Do not deliver raw local extractive summaries as the final answer when they read like repeated keywords or filler phrases. Read the transcript and rewrite `summary.md` for the actual video type.

For unboxing, card opening, product review, shopping guide, or merchandise videos, use this structure:

- One-sentence summary
- Main content
- Highlights
- Notable products or moments
- Segment-by-segment summary with timestamps
- Overall judgment or buyer takeaway

For meetings or interviews, use agenda/topics, decisions, action items, risks, and follow-ups instead.

For lectures or tutorials, use core thesis, concepts explained, step-by-step flow, examples, and takeaways.

## Quality Tips

- Provide `--language zh`, `--language en`, or another ISO-639-1 code when the language is known.
- Use `--download-tool direct` for direct MP4/MP3/WAV URLs and `--download-tool yt-dlp` for platform pages.
- Use `--cookies cookies.txt` or `--cookies-from-browser chrome` only when the user owns the account/session needed to access the video.
- Add `--prompt "Names: ...; terms: ..."` for people, brands, game titles, technical terms, or mixed-language content.
- Shorten `--chunk-minutes` for noisy media, music-heavy audio, overlapping speakers, or API file-size issues.
- Keep chunk boundaries visible in the final report; do not merge summaries so aggressively that source traceability is lost.
- Treat local summaries as extractive rough summaries; use the OpenAI engine for polished, abstractive summaries.
- When local summaries miss the point, rewrite them from the transcript rather than trying to tune keyword extraction.
- When summaries need to follow a house style, rerun only the summary step by reusing `transcript.json` as source material if practical.

## References

Read `references/model-and-dependency-notes.md` when choosing models, troubleshooting upload limits, or explaining prerequisites.
