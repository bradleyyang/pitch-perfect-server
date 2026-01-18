import json
import os
import syllables
import librosa
import numpy as np
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError
from google import genai
import fitz  # PyMuPDF for PDF processing

from app.gemini_transcription import gemini_transcribe_audio

load_dotenv()
elevenlabs = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SLOW_SPM = 130
IDEAL_SPM = 300
FAST_SPM = 400


def speech_to_text(audio_path: str):
    transcription_text = ""
    analysis_words = []
    timestamps = []
    source = "elevenlabs"

    try:
        with open(audio_path, "rb") as audio_data:
            transcription = elevenlabs.speech_to_text.convert(
                file=audio_data,
                model_id="scribe_v2",
            )

        for word in getattr(transcription, "words", []):
            duration = word.end - word.start
            if duration <= 0 or not word.text.strip():
                continue

            syllable_count = syllables.estimate(word.text) or 1
            spm = (syllable_count / duration) * 60

            if spm < SLOW_SPM:
                speed = "Too Slow"
            elif spm <= IDEAL_SPM:
                speed = "Ideal"
            elif spm <= FAST_SPM:
                speed = "Fast"
            else:
                speed = "Too Fast"

            analysis_words.append({
                "word": word.text,
                "speed": speed,
                "syllables_per_minute": round(spm, 2)
            })

            timestamps.append([word.end, round(spm, 2)])

        transcription_text = transcription.text
    except ApiError:
        source = "gemini"
        fallback = gemini_transcribe_audio(
            audio_path,
            metadata={"filename": os.path.basename(audio_path)},
        )
        transcription_text = fallback["transcription"]

    loudness = track_loudness_deviation(audio_path)

    return {
        "transcription": transcription_text,
        "word_analysis": analysis_words,
        "timestamps": timestamps,
        "loudness": loudness,
        "source": source,
    }


def track_loudness_deviation(audio_path: str, frame_length: int = 512, hop_length: int = 256):
    """Track loudness deviation over time in audio file."""
    y, sr = librosa.load(audio_path, sr=None)
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    rms_db = librosa.amplitude_to_db(rms, ref=np.max)
    times = librosa.times_like(rms_db, sr=sr, hop_length=hop_length)

    return [[float(time), float(db)] for time, db in zip(times, rms_db)]


FILLER_WORDS = {"um", "uh", "like", "so", "actually", "you know"}


def summarize_speech_with_gemini(transcription_result: dict, filename: str) -> str:
    """Use Gemini to summarize and critique speech performance."""
    transcript = transcription_result.get("transcription", "").strip()
    word_analysis = transcription_result.get("word_analysis", [])

    speech_features = []
    for word_data in word_analysis:
        speech_features.append({
            "word": word_data["word"],
            "speed": word_data["speed"],
            "is_filler": word_data["word"].lower() in FILLER_WORDS
        })

    filler_count = sum(1 for f in speech_features if f.get("is_filler"))
    speed_distribution = {}
    for w in word_analysis:
        speed = w["speed"]
        speed_distribution[speed] = speed_distribution.get(speed, 0) + 1

    audio_data = {
        "file_name": filename,
        "word_count": len(transcript.split()),
        "filler_words_count": filler_count,
        "speed_distribution": speed_distribution,
        "transcript_snippet": transcript[:500] if len(transcript) > 500 else transcript
    }

    prompt = f"""
You are an expert presentation coach. Analyze this speech performance and provide:
1. Overall summary focusing on speech clarity, pacing, filler words, and structure.
2. Specific strengths observed.
3. Areas for improvement with actionable suggestions.
4. Ratings (1-5 scale) for: Clarity, Pace, Filler Word Usage, Overall Delivery.

Audio Analysis Data:
{json.dumps(audio_data, indent=2)}

Full Transcript:
{transcript}
"""

    response = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )

    return response.text


def extract_pdf_text(pdf_path: str) -> dict:
    """Extract text and metadata from PDF slidedeck."""
    doc = fitz.open(pdf_path)
    pages = []

    for page_num, page in enumerate(doc, 1):
        text = page.get_text()
        pages.append({
            "page_number": page_num,
            "text": text.strip()
        })

    doc.close()

    return {
        "total_pages": len(pages),
        "pages": pages
    }


def summarize_pdf_with_gemini(pdf_content: dict, filename: str) -> str:
    """Use Gemini to summarize and critique a PDF slidedeck."""
    pages_text = "\n\n".join([
        f"--- Slide {p['page_number']} ---\n{p['text']}"
        for p in pdf_content["pages"]
    ])

    prompt = f"""
You are an expert presentation coach. Analyze this slide deck and provide:
1. Overall summary of the presentation content and flow.
2. Strengths of the slide deck (clarity, structure, visual hierarchy implied by text).
3. Areas for improvement with specific suggestions per slide if needed.
4. Ratings (1-5 scale) for: Content Quality, Structure/Flow, Clarity, Overall Effectiveness.
5. Suggestions for how to deliver this presentation verbally.

Slide Deck: {filename}
Total Slides: {pdf_content['total_pages']}

Content:
{pages_text}
"""

    response = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )

    return response.text
