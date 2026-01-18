import json
from pathlib import Path
from typing import Any, Dict, Optional

from tenacity import retry, stop_after_attempt, wait_random_exponential

from app.analysis import gemini_client, summarize_speech_with_gemini

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "audio-analysis.txt"


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _parse_json_response(text: str) -> Any:
    candidate = text.strip()
    if not candidate:
        return None

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {"raw_text": candidate}


@retry(
    wait=wait_random_exponential(min=1, max=5),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _generate_audio_analysis(prompt: str) -> Any:
    return gemini_client.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=prompt,
    )


def analyze_audio_with_gemini(
    audio_path: str,
    transcription: Dict[str, Any],
    filename: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio file not found at {audio_path}")

    metadata_json = json.dumps(metadata or {}, indent=2)
    summary_text = summarize_speech_with_gemini(transcription, filename)
    prompt_template = _load_prompt()
    prompt = prompt_template.format(
        audio_filename=filename,
        transcript=transcription["transcription"],
        summary=summary_text,
        metadata=metadata_json,
    )

    response = _generate_audio_analysis(prompt)
    parsed = _parse_json_response(response.text)
    return {
        "summary": summary_text,
        "analysis": parsed,
        "raw": response.text.strip(),
    }
