from fastapi import FastAPI, UploadFile, File, HTTPException
import tempfile
import os
from app.analysis import speech_to_text
from google import genai
from google.genai import types
import json

app = FastAPI()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

ALLOWED_AUDIO_TYPES = ["audio/mpeg", "audio/mp3", "audio/wav", "video/mp4"]
FILLER_WORDS = {"um", "uh", "like", "so", "actually", "you know"}

@app.get("/")
def health_check():
    return {"status": "ok"}


@app.post("/analyze-speech")
async def analyze_speech(file: UploadFile = File(...)):
    if file.content_type not in [
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "video/mp4"
    ]:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    suffix = os.path.splitext(file.filename)[-1]

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        result = speech_to_text(tmp_path)
        return result
    finally:
        os.remove(tmp_path)


@app.post("/summarize-with-gemini")
async def summarize_with_gemini(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    suffix = os.path.splitext(file.filename)[-1]

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        transcription_result = speech_to_text(tmp_path)

        transcript = transcription_result.get("Transcription", "").strip()
        word_analysis = transcription_result.get("Word Analysis", [])
        timestamps = transcription_result.get("Timestamps", [])

        speech_features = []
        for i, word_data in enumerate(word_analysis):
            speech_features.append({
                "timestamp": timestamps[i][0] if i < len(timestamps) else 0,
                "clarity": 4,  # default
                "pace": 3,     # default
                "fillers": 1 if word_data["word"].lower() in FILLER_WORDS else 0,
                "structure": 4 # default
            })

        if not speech_features:
            speech_features = [{"timestamp": 0, "clarity": 4, "pace": 3, "fillers": 0, "structure": 4}]

        audio_data = {
            "file_name": file.filename,
            "duration_sec": len(transcript.split()) / 2,  # rough estimate: 2 words/sec
            "transcript_snippet": transcript[:200],
            "word_count": len(transcript.split()),
            "filler_words_count": sum(f.get("fillers", 0) for f in speech_features),
            "average_clarity": round(sum(f.get("clarity", 4) for f in speech_features)/len(speech_features), 1)
        }

        prompt = f"""
You are a presentation coach. Summarize the performance of this audio clip.
Focus on speech clarity, pacing, filler words, and structure. Provide:
1. Overall summary
2. Strengths and weaknesses
3. Ratings (1-5)

Audio Stats:
{json.dumps(audio_data, indent=2)}
"""

        # 3. Send request to Gemini
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents={prompt}
        )

        summary = response.text
        return {"summary": summary, "transcription": transcription_result}

    finally:
        os.remove(tmp_path)