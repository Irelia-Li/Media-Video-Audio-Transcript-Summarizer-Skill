# Media Transcript Summarizer Skill

English | 中文

If you find this project helpful, please give it a star! ⭐

A structured media transcription and summarization skill for Codex. It supports extracting spoken text from uploaded audio/video files and online video links, generating timestamped transcripts, splitting long media into chunks, and producing both overall summaries and per-chunk summaries.

The skill can work locally with `faster-whisper` without an API key, or use OpenAI models for higher-quality transcription and summaries.

## Install

`media-transcript-summarizer` is distributed as a Codex skill.

Copy it into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
cp -r media-transcript-summarizer ~/.codex/skills/
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills"
Copy-Item -Recurse ".\media-transcript-summarizer" "$env:USERPROFILE\.codex\skills\"
```

Install optional dependencies:

```bash
pip install yt-dlp faster-whisper
```

Recommended for video files and long media:

```bash
# Install FFmpeg and make sure ffmpeg / ffprobe are available in PATH
```

Optional OpenAI mode:

```bash
export OPENAI_API_KEY="YOUR_KEY"
```

Windows PowerShell:

```powershell
$env:OPENAI_API_KEY="YOUR_KEY"
```

## What Is It?

Media Transcript Summarizer is a Codex skill for extracting spoken text from uploaded audio/video files and online video links.

It can download supported video links, transcribe the audio track into timestamped text, split long media into chunks, generate per-chunk and overall summaries, and export results as Markdown, TXT, JSON, CSV, and SRT subtitles.

## Key Features

- Uploaded audio/video transcription
- Online video link extraction with `yt-dlp`
- Bilibili, YouTube, Vimeo, and other supported media platforms
- Chinese and multilingual speech recognition
- Timestamped transcript generation
- Long-media chunking
- Per-chunk summaries
- Overall content summaries
- Editorial summaries for reviews, unboxing, card-opening, and shopping guide videos
- Subtitle export as `.srt`
- Structured export as `.json`
- Spreadsheet-friendly export as `.csv`
- Local offline transcription without an API key
- Optional OpenAI-powered transcription and summarization

## How It’s Wired

`audio/video file or online link` → `yt-dlp download or local file input` → `audio preparation` → `speech transcription` → `timestamped segments` → `chunk splitting` → `summary generation` → `Markdown / TXT / JSON / CSV / SRT export`

Local mode uses `faster-whisper` for speech recognition and extractive summary drafts. Codex can then rewrite the summary into a human editorial format based on the actual video type.

OpenAI mode uses OpenAI models for more accurate transcription and more natural summaries.

## Quickstart

Transcribe an uploaded audio file:

```bash
python scripts/transcribe_media.py audio.m4a --engine local --language zh
```

Transcribe an uploaded video file:

```bash
python scripts/transcribe_media.py video.mp4 --engine local --language zh
```

Extract text from an online video link:

```bash
python scripts/transcribe_media.py "https://www.bilibili.com/video/BVxxxx/" \
  --download-tool yt-dlp \
  --engine local \
  --language zh
```

Use OpenAI mode:

```bash
python scripts/transcribe_media.py video.mp4 \
  --engine openai \
  --language zh \
  --transcribe-model gpt-4o-transcribe \
  --summary-model gpt-4o-mini
```

## Usage

```bash
python scripts/transcribe_media.py <audio-file | video-file | video-link> [options]
```

Common options:

```bash
--engine local                  # local faster-whisper transcription
--engine openai                 # OpenAI transcription and summaries
--language zh                   # language hint
--chunk-minutes 5               # split transcript into 5-minute chunks
--download-tool yt-dlp          # use yt-dlp for video links
--download-format 30280         # choose audio format for Bilibili
--summary-language zh           # summary language
--timestamps segment            # segment timestamps
```

## Output Files

The skill generates:

```text
summary.md       # main content, highlights, and chunk summaries
transcript.md    # full timestamped transcript with summaries
transcript.txt   # plain transcript text
transcript.json  # structured transcript, segments, metadata, summaries
transcript.csv   # chunk-level spreadsheet-friendly output
subtitles.srt    # subtitle file
```

## Example

Extract and summarize a Bilibili video:

```bash
python scripts/transcribe_media.py "https://www.bilibili.com/video/BV1UARuBCEop/" \
  --download-tool yt-dlp \
  --download-format 30280 \
  --engine local \
  --local-model base \
  --language zh \
  --chunk-minutes 5
```

What happens:

1. The video link is downloaded as audio.
2. Speech is transcribed into timestamped text.
3. The transcript is split into chunks.
4. Each chunk gets a summary draft.
5. Codex rewrites the summary into main content and highlights when needed.
6. All outputs are exported to Markdown, TXT, JSON, CSV, and SRT.

## Summary Style

For product reviews, unboxing videos, card-opening videos, shopping guide videos, and similar content, the final summary should include:

- One-sentence summary
- Main content
- Key highlights
- Notable products or moments
- Segment-by-segment timeline
- Overall judgment or buyer takeaway

For meetings, interviews, and lectures, the summary should focus on:

- Main topics
- Important points
- Decisions
- Action items
- Key arguments
- Takeaways

## Notes

- This skill extracts spoken text from the audio track of audio/video files.
- It supports both uploaded media files and online media links.
- OCR for text displayed visually inside video frames is not the default workflow.
- Local mode does not require an OpenAI API key.
- OpenAI mode is recommended for higher accuracy and more polished summaries.
- For private or login-only videos, use cookies only when you are authorized to access the content.

## Need Help?

Ask Codex:

```text
Help me use the media transcript summarizer skill to extract text from a video link and generate a summary.
```

```text
Use the media transcript summarizer skill to transcribe this uploaded video and summarize the main content.
```

## License

MIT
