import os
import syllables
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()
elevenlabs = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

SLOW_SPM = 130
IDEAL_SPM = 300
FAST_SPM = 400


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

    return {
        "Transcription": transcription.text,
        "Word Analysis": analysis_words,
        "Timestamps": timestamps
    }
