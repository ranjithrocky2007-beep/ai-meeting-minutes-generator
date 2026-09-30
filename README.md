# Meeting Summarizer

A full-stack application that accepts a meeting video or audio file, transcribes it using **OpenAI Whisper** (open-source), and generates a structured summary using **facebook/bart-large-cnn** — no paid API keys required.

---

## Project Structure

```
meeting-summarizer/
├── backend/
│   ├── main.py            # FastAPI app — upload, transcribe, summarize
│   └── uploads/           # Temp storage (auto-cleaned after each request)
├── frontend/
│   └── index.html         # Single-page UI (drag-drop upload + results)
├── Dockerfile             # Container definition (Red Hat UBI9, non-root)
├── docker-compose.yml     # One-command Docker launcher
├── requirements.txt       # Pinned Python dependencies
├── start.sh               # Local launcher (no Docker)
└── README.md
```

---

## ▶ Option 1: Run with Docker (Recommended — works on any system)

This is the best way to share the app. The other person only needs **Docker Desktop** installed — nothing else.

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — free, available for Mac, Windows, and Linux

### Steps

```bash
# 1. Clone or copy the project folder to their machine
cd meeting-summarizer

# 2. Build the image (first time only — downloads ~2 GB of models into the image)
docker compose build

# 3. Start the app
docker compose up
```

Open **http://localhost:8000** in any browser.

```bash
# Stop the app
docker compose down
```

### Share with someone else

```bash
# Save the image to a file and send it
docker save meeting-summarizer:latest | gzip > meeting-summarizer.tar.gz

# The other person loads and runs it (no build needed)
docker load < meeting-summarizer.tar.gz
docker compose up
```

> **First `docker compose build` takes 10–20 minutes** — it downloads Python, ffmpeg, Whisper, and BART once and bakes them into the image. Every subsequent `docker compose up` starts in seconds.

---

## ▶ Option 2: Run Locally (macOS / Linux / WSL2 only)

### Prerequisites
- Python 3.10+
- ffmpeg: `brew install ffmpeg` (macOS) / `sudo apt install ffmpeg` (Linux)

### Steps

```bash
cd meeting-summarizer
chmod +x start.sh
./start.sh
```

Open **http://127.0.0.1:8000**

> First run downloads Whisper (~140 MB) and BART (~1.6 GB) into `~/.cache/huggingface/`. Only happens once.

---

## API Reference

### `POST /api/summarize`

Upload a meeting file and receive a transcript + summary.

**Request:** `multipart/form-data`
- `file` — video or audio file (MP4, AVI, MOV, MKV, WebM, MP3, WAV, M4A) up to 500 MB

**Response (JSON):**
```json
{
  "filename": "weekly-sync.mp4",
  "transcript": "Good morning everyone. Today we'll be discussing...",
  "summary": "The team discussed quarterly targets, assigned action items...",
  "duration_seconds": 1823.4
}
```

### `GET /health`
```json
{ "status": "ok" }
```

---

## Supported File Formats

`MP4` `AVI` `MOV` `MKV` `WebM` `MP3` `WAV` `M4A`

---

## AI Models (100% Free & Open-Source)

| Task | Model | License |
|---|---|---|
| Speech-to-text | `openai/whisper-base` | MIT |
| Summarization | `facebook/bart-large-cnn` | MIT |

---

## System Requirements

| Resource | Minimum | Recommended |
|---|---|---|
| RAM | 8 GB | 16 GB |
| Disk | 4 GB free | 6 GB free |
| CPU | 4-core | 8-core |

---

## Security Notes

- Server binds to `127.0.0.1` (local) — not exposed to the network
- Uploaded files are deleted immediately after processing
- Container runs as non-root user (UID 1001)
- No API keys or secrets required
