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


FILLER_WORDS = {    "um",
    "uh",
    "uhh",
    "uhm",
    "erm",
    "like",
    "so",
    "actually",
    "you know",
    "basically",
    "literally",
    "kinda",
    "sorta",
    "i mean",
    "you see",
    "right",
    "okay",
    "ok",
    "well",
    "just",
    "stuff",
    "things",
    "maybe",
}


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

    prompt = f"""
        You are an expert, direct pitch coach. Respond with crisp sections (no code fences). Ground every point in the transcript and numbers below. Be specific and tactical.
        
        Audio Analysis Data (pace/fillers derived, do not re-infer):
        {json.dumps(audio_data, indent=2)}
        
        Full Transcript:
        {transcript}
        
        Return exactly these sections in plain text (no extra prose):
        HEADLINE: one sentence that names the single biggest win and single biggest fix; include who benefits.
        METRICS: pace buckets and filler count from Audio Analysis Data (do not restate the whole transcript).
        STRENGTHS (3 bullets): each cites a short quote (<12 words) from the transcript and why it works (metric, proof, or clarity).
        ISSUES (3 bullets): each cites the problematic phrase and ends with a concrete fix (e.g., "Replace X with Y" or "Pause 0.5s after claim Z").
        ACTION PLAN (5 numbered items): prioritized; each includes owner (presenter or script), what to change, and expected impact (e.g., +clarity, +engagement).
        RATINGS (1-5): clarity, pacing, filler control, structure, engagement – each with a 1-line justification that references transcript or metrics.
        MICRO-REWRITES (3 bullets): replacement sentences that instantly improve clarity/energy; keep them short and ready to paste into the script."""

    response = gemini_client.models.generate_content(
        model="gemini-3-flash-preview",#"gemini-2.0-flash",
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
        You are an expert presentation coach. Deliver detailed, actionable feedback for this startup pitch deck. Be specific; cite slide numbers; focus on what changes the outcome.
        
        Slide Deck: {filename}
        Total Slides: {pdf_content['total_pages']}
        
        Content:
        {pages_text}
        
        Respond with these sections (plain text, no code fences):
        HEADLINE: the single highest-leverage improvement; include slide reference if applicable.
        MISSING FUNDAMENTALS: problem, solution, traction, market, business model, moat, ask – explicitly note which are missing or weak.
        TOP STRENGTHS (3 bullets): cite slide numbers; why it works (metric, clarity, proof).
        TOP GAPS (3 bullets): cite slide numbers; include a concrete fix (rewrite/add/remove/reorder).
        PER-SLIDE NOTES: for each slide, 1 short note only if critical (skip if nothing material).
        ACTION PLAN (5 numbered items): prioritized; include owner ("deck text" or "presenter"), what to change, and expected impact (e.g., +credibility, +clarity, +conversion).
        RATINGS (1-5): content quality, structure/flow, clarity, persuasiveness, visual clarity – each with a 1-line rationale tied to the deck.
        DELIVERY TIPS: 3 bullets tailored to this deck's story (what to emphasize, pacing, proof ordering)."""

    response = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )

    return response.text
