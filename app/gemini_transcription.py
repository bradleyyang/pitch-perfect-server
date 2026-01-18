import base64
import json
import os
from pathlib import Path
from typing import Dict, Optional

import requests

DEFAULT_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5:transcribe"  # assume generative language STT endpoint
)


def gemini_transcribe_audio(
    audio_path: str,
    language_code: str = "en-US",
    metadata: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Send audio bytes to the Gemini speech-to-text endpoint."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for Gemini transcription.")

    endpoint = os.getenv("GEMINI_STT_ENDPOINT", DEFAULT_ENDPOINT).rstrip("/")
    url = f"{endpoint}?key={api_key}"

    with open(audio_path, "rb") as handle:
        payload = handle.read()
    encoded = base64.b64encode(payload).decode("ascii")

    body = {
        "config": {
            "languageCode": language_code,
            "metadata": metadata or {},
        },
        "audio": {"content": encoded},
    }

    response = requests.post(url, json=body)
    response.raise_for_status()

    data = response.json()
    transcript = data.get("transcript")
    if not transcript:
        # Some endpoints return results structure
        results = data.get("results", [])
        transcript_chunks = []
        for item in results:
            for alt in item.get("alternatives", []):
                text = alt.get("transcript")
                if text:
                    transcript_chunks.append(text)
        transcript = " ".join(transcript_chunks)

    if not transcript:
        raise RuntimeError("Gemini transcription returned no text.")

    return {
        "transcription": transcript,
        "raw": data,
    }
