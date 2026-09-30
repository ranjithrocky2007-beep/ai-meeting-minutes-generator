import os
import uuid
import logging
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

import whisper
from transformers import pipeline

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".mp3", ".wav", ".m4a"}
MAX_FILE_SIZE_MB = 500
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# BART supports max ~1024 tokens; split long transcripts into chunks of ~800 words
CHUNK_WORD_LIMIT = 800

# ── Model loading (done once at startup) ─────────────────────────────────────
logger.info("Loading Whisper model (base)…")
whisper_model = whisper.load_model("base")
logger.info("Whisper model loaded.")

logger.info("Loading summarization pipeline (facebook/bart-large-cnn)…")
summarizer = pipeline(
    "summarization",
    model="facebook/bart-large-cnn",
    tokenizer="facebook/bart-large-cnn",
)
logger.info("Summarization pipeline ready.")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Meeting Summarizer API", version="1.0.0")

# CORS origins — allow localhost on any port so Docker port-mapping works
_CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Frontend directory — works both locally and inside Docker (/app/frontend)
_here = Path(__file__).parent          # .../backend/
_repo_root = _here.parent              # .../meeting-summarizer/ or /app
FRONTEND_DIR = _repo_root / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ── Response models ───────────────────────────────────────────────────────────
class SummaryResponse(BaseModel):
    filename: str
    transcript: str
    summary: str
    duration_seconds: float | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_file(filename: str, size: int) -> None:
    """Raise HTTPException for unsupported type or oversized file."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )
    if size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_MB} MB.",
        )


def _extract_audio(video_path: Path, audio_path: Path) -> None:
    """Use ffmpeg to strip audio from a video file into a WAV file."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",                   # no video
        "-ar", "16000",          # 16 kHz — optimal for Whisper
        "-ac", "1",              # mono
        "-f", "wav",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("ffmpeg error: %s", result.stderr)
        raise HTTPException(status_code=500, detail="Audio extraction failed.")


def _chunk_text(text: str, word_limit: int) -> list[str]:
    """Split text into chunks that fit within BART's token window."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), word_limit):
        chunks.append(" ".join(words[i : i + word_limit]))
    return chunks


def _summarize_text(text: str) -> str:
    """Summarize text, chunking if necessary."""
    chunks = _chunk_text(text, CHUNK_WORD_LIMIT)
    summaries = []
    for idx, chunk in enumerate(chunks):
        logger.info("Summarizing chunk %d/%d…", idx + 1, len(chunks))
        result = summarizer(
            chunk,
            max_length=200,
            min_length=40,
            do_sample=False,
        )
        summaries.append(result[0]["summary_text"])

    # If multiple chunks, do a second-pass summary of the combined summaries
    if len(summaries) > 1:
        combined = " ".join(summaries)
        logger.info("Second-pass summary over %d chunk summaries…", len(summaries))
        final = summarizer(combined, max_length=300, min_length=60, do_sample=False)
        return final[0]["summary_text"]

    return summaries[0]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_frontend():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/summarize", response_model=SummaryResponse)
async def summarize_meeting(file: UploadFile = File(...)):
    """
    Upload a meeting video or audio file.
    Returns the full transcript and an AI-generated summary.
    """
    content = await file.read()
    _validate_file(file.filename or "upload", len(content))

    safe_name = f"{uuid.uuid4().hex}{Path(file.filename or 'upload').suffix.lower()}"
    saved_path = UPLOAD_DIR / safe_name

    try:
        # Persist upload
        saved_path.write_bytes(content)
        logger.info("Saved upload: %s (%d bytes)", safe_name, len(content))

        ext = Path(file.filename or "").suffix.lower()
        audio_extensions = {".mp3", ".wav", ".m4a"}

        if ext in audio_extensions:
            audio_path = saved_path
        else:
            # Extract audio from video
            audio_path = UPLOAD_DIR / f"{safe_name}.wav"
            _extract_audio(saved_path, audio_path)

        # Transcribe
        logger.info("Transcribing with Whisper…")
        result = whisper_model.transcribe(str(audio_path), fp16=False)
        transcript: str = result["text"].strip()
        duration: float | None = result.get("segments", [{}])[-1].get("end") if result.get("segments") else None

        if not transcript:
            raise HTTPException(status_code=422, detail="No speech detected in the uploaded file.")

        logger.info("Transcript length: %d characters", len(transcript))

        # Summarize
        summary = _summarize_text(transcript)
        logger.info("Summary generated successfully.")

        return SummaryResponse(
            filename=file.filename or safe_name,
            transcript=transcript,
            summary=summary,
            duration_seconds=duration,
        )

    finally:
        # Clean up files to save disk space
        if saved_path.exists():
            saved_path.unlink()
        wav_path = UPLOAD_DIR / f"{safe_name}.wav"
        if wav_path.exists() and wav_path != saved_path:
            wav_path.unlink()
