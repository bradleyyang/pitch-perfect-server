import os
import json
import syllables
import librosa
import numpy as np
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from google import genai
import fitz  # PyMuPDF for PDF processing

load_dotenv()
elevenlabs = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SLOW_SPM = 130
IDEAL_SPM = 300
FAST_SPM = 400

DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"


def text_to_speech(text: str, voice_id: str = None) -> bytes:
    """Convert text to speech. Uses default voice if voice_id not provided."""
    tts_response = elevenlabs.text_to_speech.convert(
        voice_id=voice_id or DEFAULT_VOICE_ID,
        output_format="mp3_44100_128",
        text=text,
        model_id="eleven_multilingual_v2"
    )

    if hasattr(tts_response, "__iter__"):
        audio_bytes = b"".join(chunk for chunk in tts_response)
    else:
        audio_bytes = tts_response.read() if hasattr(tts_response, "read") else tts_response

    return audio_bytes


def speech_to_text(audio_path: str):
    with open(audio_path, "rb") as audio_data:
        transcription = elevenlabs.speech_to_text.convert(
            file=audio_data,
            model_id="scribe_v2",
        )

    analysis_words = []
    timestamps = []

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

    loudness = track_loudness_deviation(audio_path)

    return {
        "transcription": transcription.text,
        "word_analysis": analysis_words,
        "timestamps": timestamps,
        "loudness": loudness
    }


def track_loudness_deviation(audio_path: str, frame_length: int = 512, hop_length: int = 256):
    """Track loudness deviation over time in audio file."""
    y, sr = librosa.load(audio_path, sr=None)
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    rms_db = librosa.amplitude_to_db(rms, ref=np.max)
    times = librosa.times_like(rms_db, sr=sr, hop_length=hop_length)

    return [[float(time), float(db)] for time, db in zip(times, rms_db)]


FILLER_WORDS = {"um", "uh", "like", "so", "actually", "you know", "basically", "literally"}


def summarize_speech_with_gemini(transcription_result: dict, filename: str) -> dict:
    """Use Gemini to analyze speech and return structured insights."""
    transcript = transcription_result.get("transcription", "").strip()
    word_analysis = transcription_result.get("word_analysis", [])

    filler_count = sum(1 for w in word_analysis if w["word"].lower() in FILLER_WORDS)
    speed_distribution = {}
    for w in word_analysis:
        speed = w["speed"]
        speed_distribution[speed] = speed_distribution.get(speed, 0) + 1

    audio_data = {
        "word_count": len(transcript.split()),
        "filler_words_count": filler_count,
        "speed_distribution": speed_distribution
    }

    prompt = f"""You are a direct, honest presentation coach. Analyze this pitch and respond ONLY with valid JSON (no markdown, no code blocks).

Audio Stats: {json.dumps(audio_data)}
Transcript: {transcript}

Return this exact JSON structure:
{{
  "overall_verdict": "1-2 sentences. Be honest and direct about the pitch quality. Start with the most important observation.",
  "clarity": {{
    "score": 1-5,
    "insight": "1 sentence on speech clarity",
    "action": "1 specific action to improve"
  }},
  "pacing": {{
    "score": 1-5,
    "insight": "1 sentence on speaking pace",
    "action": "1 specific action to improve"
  }},
  "filler_words": {{
    "score": 1-5,
    "count": {filler_count},
    "insight": "1 sentence on filler word usage",
    "action": "1 specific action to reduce fillers"
  }},
  "structure": {{
    "score": 1-5,
    "insight": "1 sentence on pitch structure/flow",
    "action": "1 specific action to improve structure"
  }},
  "engagement": {{
    "score": 1-5,
    "insight": "1 sentence on audience engagement potential",
    "action": "1 specific action to boost engagement"
  }}
}}"""

    response = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )

    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        cleaned = response.text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(cleaned)


def clone_voice(audio_path: str, name: str = "pitch_voice") -> str:
    """Clone voice from audio file and return voice_id."""
    with open(audio_path, "rb") as f:
        voice = elevenlabs.clone(
            name=name,
            files=[f],
            description="Cloned voice for pitch feedback"
        )
    return voice.voice_id


def delete_cloned_voice(voice_id: str):
    """Delete a cloned voice to clean up."""
    try:
        elevenlabs.voices.delete(voice_id=voice_id)
    except Exception:
        pass


def generate_improved_pitch(transcript: str, insights: dict) -> str:
    """Use Gemini to generate an improved version of the pitch."""
    prompt = f"""You are a pitch writing expert. Rewrite this pitch to be more compelling and effective.
Keep the same core message but improve based on these insights:
- Clarity: {insights.get('clarity', {}).get('action', 'Improve clarity')}
- Structure: {insights.get('structure', {}).get('action', 'Improve structure')}
- Engagement: {insights.get('engagement', {}).get('action', 'Improve engagement')}

Original pitch:
{transcript}

Write ONLY the improved pitch text. No explanations, no commentary. Keep it concise (similar length to original)."""

    response = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    return response.text.strip()


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
