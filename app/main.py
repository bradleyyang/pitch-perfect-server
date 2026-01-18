from fastapi import FastAPI, UploadFile, File, HTTPException, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import tempfile
import os
import json
from uuid import uuid4
from typing import Optional
from app.analysis import (
    speech_to_text,
    summarize_speech_with_gemini,
    extract_pdf_text,
    summarize_pdf_with_gemini
)
from app.job_store import (
    create_job,
    get_job,
    get_result,
    persist_upload,
)
from app.agent_workflow import run_agent_workflow

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_AUDIO_TYPES = ["audio/mpeg", "audio/mp3", "audio/wav", "video/mp4"]
ALLOWED_PDF_TYPES = ["application/pdf"]


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    """
    Unified endpoint for analyzing audio/video files.
    Returns transcription, word analysis, timestamps, loudness, and Gemini summary.
    """
    if file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    suffix = os.path.splitext(file.filename)[-1]

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        transcription_result = speech_to_text(tmp_path)
        summary = summarize_speech_with_gemini(transcription_result, file.filename)

        return {
            "transcription": transcription_result["transcription"],
            "word_analysis": transcription_result["word_analysis"],
            "timestamps": transcription_result["timestamps"],
            "loudness": transcription_result["loudness"],
            "summary": summary
        }
    finally:
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


@app.post("/api/evaluate/start")
async def start_evaluation(
    background_tasks: BackgroundTasks,
    target: str = Form(...),
    context: str = Form(""),
    metadata: Optional[str] = Form(None),
    transcript: Optional[str] = Form(None),
    deck: Optional[UploadFile] = File(None),
    media: Optional[UploadFile] = File(None),
):
    """
    Kick off an evaluation job that orchestrates the multi-agent workflow.
    """
    job_id = str(uuid4())
    parsed_metadata = {}
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except ValueError:
            raise HTTPException(status_code=400, detail="Metadata must be valid JSON.")

    deck_info = None
    if deck:
        deck_bytes = await deck.read()
        deck_info = persist_upload(job_id, deck.filename, deck_bytes, deck.content_type)

    media_info = None
    if media:
        media_bytes = await media.read()
        media_info = persist_upload(job_id, media.filename, media_bytes, media.content_type)

    job_payload = {
        "target": target,
        "context": context,
        "metadata": parsed_metadata,
        "transcript": transcript,
        "transcript_source": "user" if transcript else None,
        "deck": deck_info,
        "media": media_info,
    }

    create_job(job_id, target, job_payload)
    background_tasks.add_task(run_agent_workflow, job_id, job_payload)

    return {"jobId": job_id, "statusUrl": f"/api/evaluate/status/{job_id}"}


@app.get("/api/evaluate/status/{job_id}")
def evaluation_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    result = get_result(job_id)
    return {
        "job": job,
        "result": result,
    }
