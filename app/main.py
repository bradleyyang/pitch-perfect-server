from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import tempfile
import os
import logging
from app.analysis import (
    speech_to_text,
    summarize_speech_with_gemini,
    extract_pdf_text,
    summarize_pdf_with_gemini
)
from app.evaluation import (
    InMemoryJobStore,
    process_job,
    persist_upload,
    allocate_job_space,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    # allow_origins=["http://localhost:3000", "https://pitch-perfect-cg8p3t7pt-bradley-yangs-projects.vercel.app"],
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_AUDIO_TYPES = ["audio/mpeg", "audio/mp3", "audio/wav", "video/mp4", "audio/webm", "video/webm"]
ALLOWED_PDF_TYPES = ["application/pdf"]

job_store = InMemoryJobStore()


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.post("/api/evaluate/start")
async def start_evaluation(
    background_tasks: BackgroundTasks,
    deck: UploadFile | None = File(default=None),
    transcript: str | None = Form(default=None),
    media: UploadFile | None = File(default=None),
):
    """Kick off simplified evaluation job. Uses in-memory job store (no persistence)."""
    if not any([deck, transcript, media]):
        raise HTTPException(status_code=400, detail="Provide at least one of deck, transcript, or media.")

    job_id = job_store.create_job()
    temp_dir = allocate_job_space(job_id)
    job_store.attach_paths(job_id, {"temp_dir": temp_dir})

    deck_path = None
    media_path = None

    if deck:
        suffix = os.path.splitext(deck.filename or "")[-1] or ".pdf"
        deck_bytes = await deck.read()
        deck_path = persist_upload(deck_bytes, temp_dir, f"deck{suffix}")

    if media:
        suffix = os.path.splitext(media.filename or "")[-1] or ".media"
        media_bytes = await media.read()
        media_path = persist_upload(media_bytes, temp_dir, f"media{suffix}")

    background_tasks.add_task(process_job, job_store, job_id, deck_path, transcript, media_path)
    return {"jobId": job_id, "status": "pending"}


@app.get("/api/evaluate/status/{job_id}")
def get_status(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.setdefault("jobId", job.get("id"))
    return job


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    """
    Unified endpoint for analyzing audio/video files.
    Returns transcription, word analysis, timestamps, loudness, and Gemini summary.
    """
    if file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    suffix = os.path.splitext(file.filename)[-1]
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        logger.info(f"Processing audio file: {file.filename}, content_type: {file.content_type}")

        transcription_result = speech_to_text(tmp_path)
        logger.info("Transcription completed successfully")

        summary = summarize_speech_with_gemini(transcription_result, file.filename)
        logger.info("Gemini summary completed successfully")

        return {
            "transcription": transcription_result["transcription"],
            "word_analysis": transcription_result["word_analysis"],
            "timestamps": transcription_result["timestamps"],
            "loudness": transcription_result["loudness"],
            "summary": summary
        }
    except Exception as e:
        logger.error(f"Error processing audio: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "detail": "Failed to process audio file"}
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/analyze-pdf")
async def analyze_pdf(file: UploadFile = File(...)):
    """
    Endpoint for analyzing PDF slidedecks.
    Returns extracted text per page and Gemini summary/critique.
    """
    if file.content_type not in ALLOWED_PDF_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload a PDF.")

    suffix = os.path.splitext(file.filename)[-1]

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        pdf_content = extract_pdf_text(tmp_path)
        summary = summarize_pdf_with_gemini(pdf_content, file.filename)

        return {
            "total_pages": pdf_content["total_pages"],
            "pages": pdf_content["pages"],
            "summary": summary
        }
    finally:
        os.remove(tmp_path)
