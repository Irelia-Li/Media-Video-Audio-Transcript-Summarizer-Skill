# Model and Dependency Notes

## OpenAI audio transcription

The OpenAI audio transcription endpoint accepts common audio/video container uploads and supports models including:

- `gpt-4o-mini-transcribe`
- `gpt-4o-transcribe`
- `gpt-4o-transcribe-diarize`
- `whisper-1`

Use the current OpenAI docs when exact model availability, parameter support, pricing, or upload limits matter:

- Speech to text guide: https://platform.openai.com/docs/guides/speech-to-text
- Audio transcription API reference: https://platform.openai.com/docs/api-reference/audio/createTranscription
- Audio overview: https://platform.openai.com/docs/guides/audio

As of the checked docs, uploads are limited to 25 MB per transcription request. Chunk media before upload when needed.

## Timestamp behavior

`gpt-4o-transcribe` and `gpt-4o-mini-transcribe` return transcript text in JSON. Use chunk-level timestamps from local splitting.

Use `whisper-1` with `response_format=verbose_json` and `timestamp_granularities[]=segment` when segment timestamps are required.

Use `gpt-4o-transcribe-diarize` with `response_format=diarized_json` and `chunking_strategy=auto` when speaker labels are required.

## Local transcription

Use local transcription when the user cannot provide an OpenAI API key or wants to keep audio on the machine:

```bash
python -m pip install faster-whisper
python scripts/transcribe_media.py audio.m4a --engine local --language zh
```

Local mode uses `faster-whisper` and supports `--local-model tiny|base|small|medium|large-v3` or a compatible model name. `small` is a reasonable first pass for Chinese. Use a larger model for noisy, overlapping, or domain-specific speech if runtime is acceptable.

Local mode writes transcript files, per-chunk extractive summaries, and an overall extractive summary. These summaries select representative transcript lines and frequent terms; use the OpenAI engine when polished abstractive summaries are required.

## FFmpeg

Install FFmpeg for video files and long media:

- Windows: install with winget, Chocolatey, or a static build, then make `ffmpeg.exe` and `ffprobe.exe` available on `PATH`.
- macOS: `brew install ffmpeg`.
- Linux: install with the system package manager, for example `apt install ffmpeg`.

Without FFmpeg, the bundled script can only upload one already-supported media file directly, and only if it is under the upload size limit.

## URL downloads

For direct media links ending in formats such as `.mp4`, `.mp3`, `.m4a`, `.wav`, or `.webm`, the script can download with plain HTTP.

For platform pages such as YouTube, Bilibili, Vimeo, X/Twitter, TikTok, or sites that require media extraction, install `yt-dlp` and keep it current:

```bash
python -m pip install -U yt-dlp
```

Use cookies only for content the user is authorized to access:

```bash
python scripts/transcribe_media.py "https://example.com/private-video" --cookies cookies.txt
python scripts/transcribe_media.py "https://example.com/private-video" --cookies-from-browser chrome
```

If a link downloads an HTML page instead of a media file, rerun with `--download-tool yt-dlp`.
