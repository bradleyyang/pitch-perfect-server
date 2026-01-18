from fastapi import FastAPI, UploadFile, File, HTTPException
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
