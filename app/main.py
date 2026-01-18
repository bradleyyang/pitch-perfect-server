import base64
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import tempfile
import os
import logging
from app.analysis import (
    speech_to_text,
    summarize_speech_with_gemini,
    extract_pdf_text,
    summarize_pdf_with_gemini,
    text_to_speech,
    clone_voice,
    delete_cloned_voice,
    generate_improved_pitch
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_AUDIO_TYPES = ["audio/mpeg", "audio/mp3", "audio/wav", "video/mp4", "audio/webm", "video/webm"]
ALLOWED_PDF_TYPES = ["application/pdf"]


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    """
    Analyze audio/video pitch and return structured insights.
    Returns transcription, metrics, modular insights, and audio verdict.
    """
    if file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    suffix = os.path.splitext(file.filename)[-1]
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        logger.info(f"Processing audio file: {file.filename}")

        transcription_result = speech_to_text(tmp_path)
        logger.info("Transcription completed")

        insights = summarize_speech_with_gemini(transcription_result, file.filename)
        logger.info("Insights generated")

        verdict_audio = text_to_speech(insights.get("overall_verdict", "Analysis complete."))
        verdict_audio_base64 = base64.b64encode(verdict_audio).decode("utf-8")

        return {
            "transcription": transcription_result["transcription"],
            "word_analysis": transcription_result["word_analysis"],
            "timestamps": transcription_result["timestamps"],
            "loudness": transcription_result["loudness"],
            "insights": insights,
            "verdict_audio": verdict_audio_base64
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


class ImprovedPitchRequest(BaseModel):
    transcript: str
    insights: dict


@app.post("/generate-improved-pitch")
async def improved_pitch_endpoint(file: UploadFile = File(...), transcript: str = "", insights_json: str = "{}"):
    """
    Generate improved pitch audio using the user's cloned voice.
    Requires original audio (for voice cloning), transcript, and insights.
    """
    import json

    if file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    suffix = os.path.splitext(file.filename)[-1]
    tmp_path = None
    voice_id = None

    try:
        insights = json.loads(insights_json) if insights_json else {}

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        logger.info("Cloning voice from audio")
        voice_id = clone_voice(tmp_path, name=f"pitch_{file.filename[:10]}")
        logger.info(f"Voice cloned: {voice_id}")

        improved_text = generate_improved_pitch(transcript, insights)
        logger.info("Improved pitch text generated")

        improved_audio = text_to_speech(improved_text, voice_id=voice_id)
        improved_audio_base64 = base64.b64encode(improved_audio).decode("utf-8")

        return {
            "improved_text": improved_text,
            "improved_audio": improved_audio_base64
        }
    except Exception as e:
        logger.error(f"Error generating improved pitch: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "detail": "Failed to generate improved pitch"}
        )
    finally:
        if voice_id:
            delete_cloned_voice(voice_id)
            logger.info(f"Cloned voice deleted: {voice_id}")
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/analyze-pdf")
async def analyze_pdf(file: UploadFile = File(...)):
    """
    Analyze PDF slidedeck and return structured insights.
    """
    if file.content_type not in ALLOWED_PDF_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload a PDF.")

    suffix = os.path.splitext(file.filename)[-1]
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        pdf_content = extract_pdf_text(tmp_path)
        summary = summarize_pdf_with_gemini(pdf_content, file.filename)

        return {
            "total_pages": pdf_content["total_pages"],
            "pages": pdf_content["pages"],
            "summary": summary
        }
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "detail": "Failed to process PDF"}
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
