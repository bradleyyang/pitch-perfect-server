import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

from app.analysis import (
    speech_to_text,
    extract_pdf_text,
    summarize_pdf_with_gemini,
    gemini_client,
)
from app.agent_schemas import validate_agent_output
from app.gemini_audio import analyze_audio_with_gemini
from app.lang_graph import LangGraphNode, LangGraphRunner
from app import job_store

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_FILES = {
    "deck": "deck-agent.txt",
    "text": "text-agent.txt",
    "speech_content": "speech-content-agent.txt",
    "audio": "audio-agent.txt",
    "voice": "voice-agent.txt",
    "transcription": "transcription-agent.txt",
    "combine": "combine-agent.txt",
}
AGENT_DEPENDENCIES = {
    "deck": [],
    "text": [],
    "speech_content": [],
    "audio": [],
    "voice": [],
    "transcription": [],
}


def _load_prompt(agent_name: str) -> str:
    prompt_name = PROMPT_FILES.get(agent_name)
    if not prompt_name:
        raise ValueError(f"Unknown agent prompt for {agent_name}")
    prompt_path = PROMPT_DIR / prompt_name
    return prompt_path.read_text(encoding="utf-8")


def _parse_json_response(text: str) -> Any:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Empty response yielded no JSON.")

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError("Unable to parse JSON from agent response.")


def _call_agent(agent_name: str, prompt_vars: Dict[str, Any]) -> Dict[str, Any]:
    prompt_template = _load_prompt(agent_name)
    prompt_text = prompt_template.format(**prompt_vars)
    response = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt_text,
    )
    parsed = _parse_json_response(response.text)
    validated, warnings = validate_agent_output(agent_name, parsed)
    return {"parsed": validated, "raw": response.text.strip(), "warnings": warnings}


def _make_prompt_vars(agent_name: str, context_data: Dict[str, Any]) -> Dict[str, Any]:
    base = {
        "context": context_data["context"],
        "target": context_data["target"],
        "metadata": context_data["metadata"],
    }
    if agent_name in ("text", "speech_content", "audio", "voice", "transcription"):
        base["transcript"] = context_data["transcript"]
    if agent_name == "deck":
        base["deck_text"] = context_data["deck_text"]
    if agent_name in ("audio", "voice", "transcription"):
        base["audio_summary"] = context_data["audio_summary"]
    return base


def _make_agent_compute(agent_name: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    def compute(state: Dict[str, Any]) -> Dict[str, Any]:
        prompt_vars = _make_prompt_vars(agent_name, state)
        return _call_agent(agent_name, prompt_vars)

    return compute


def _make_combine_compute() -> callable:
    def compute(state: Dict[str, Any]) -> Dict[str, Any]:
        agents_json = json.dumps(
            {name: data for name, data in state["agents"].items() if name != "combine"},
            indent=2,
        )
        prompt_vars = {
            "context": state["context"],
            "target": state["target"],
            "metadata": state["metadata"],
            "deck_summary": state["deck_summary"],
            "audio_summary": state["audio_summary"],
            "agents_json": agents_json,
        }
        return _call_agent("combine", prompt_vars)

    return compute


def execute_agent_workflow(job_payload: Dict[str, Any]) -> Dict[str, Any]:
    context = job_payload.get("context", "")
    target = job_payload.get("target", "")
    metadata = job_payload.get("metadata") or {}

    transcript_text = job_payload.get("transcript")
    media_info = job_payload.get("media")

    audio_source_name = target
    transcription_result: Dict[str, Any]

    if transcript_text:
        transcription_result = {
            "transcription": transcript_text,
            "word_analysis": [],
            "timestamps": [],
            "loudness": [],
        }
    elif media_info and media_info.get("path"):
        transcription_result = speech_to_text(media_info["path"])
        audio_source_name = media_info.get("filename") or target
    else:
        raise RuntimeError("No transcript or media available to evaluate.")

    audio_analysis: Dict[str, Any]
    if media_info and media_info.get("path"):
        audio_analysis = analyze_audio_with_gemini(
            media_info["path"],
            transcription_result,
            audio_source_name,
            metadata,
        )
    else:
        audio_analysis = {
            "summary": "Transcript-only evaluation (raw audio unavailable).",
            "analysis": {},
            "raw": "",
        }
    audio_summary = audio_analysis.get("summary", "No summary available.")

    deck_info = job_payload.get("deck")
    deck_summary = "No deck uploaded."
    deck_pages: List[Dict[str, Any]] = []
    deck_text = "No deck text provided."
    if deck_info and deck_info.get("path"):
        extracted = extract_pdf_text(deck_info["path"])
        deck_pages = extracted.get("pages", [])
        deck_text_fragments = [
            f"Slide {page.get('page_number')}: {page.get('text', '').strip()}"
            for page in deck_pages
            if page.get("text")
        ]
        deck_text = "\n\n".join(deck_text_fragments) or "Deck slides had no text."
        deck_summary = summarize_pdf_with_gemini(extracted, deck_info.get("filename") or target)

    metadata_str = json.dumps(metadata, indent=2)
    state: Dict[str, Any] = {
        "context": context,
        "target": target,
        "metadata": metadata_str,
        "transcript": transcription_result["transcription"],
        "deck_text": deck_text,
        "deck_summary": deck_summary,
        "audio_summary": audio_summary,
        "audio_analysis": audio_analysis,
        "agents": {},
        "agent_raw": {},
        "agent_warnings": {},
    }

    graph = LangGraphRunner()
    for agent_name, dependencies in AGENT_DEPENDENCIES.items():
        graph.register(
            LangGraphNode(
                name=agent_name,
                compute=_make_agent_compute(agent_name),
                dependencies=dependencies,
            )
        )

    graph.register(
        LangGraphNode(
            name="combine",
            compute=_make_combine_compute(),
            dependencies=list(AGENT_DEPENDENCIES.keys()),
        )
    )

    graph_order = graph.run(state)
    combined_agents = state["agents"]
    agent_warnings = state["agent_warnings"]
    combine_data = combined_agents["combine"]
    combine_warnings: List[str] = agent_warnings.get("combine", []).copy()
    combine_raw = state["agent_raw"].get("combine", "")
    summary_adjustments: List[Dict[str, Any]] = []

    low_agents: List[Dict[str, Any]] = []
    for agent_name, agent_data in combined_agents.items():
        overall = agent_data.get("overallScore")
        if isinstance(overall, (int, float)) and overall < 60 and agent_name != "combine":
            low_agents.append({"agent": agent_name, "score": overall})

    if low_agents:
        penalty = min(15, 5 * len(low_agents))
        original_score = combine_data["summary"]["overallScore"]
        adjusted_score = max(1, original_score - penalty)
        combine_data["summary"]["overallScore"] = adjusted_score
        summary_adjustments.append(
            {
                "penalty": penalty,
                "lowAgents": low_agents,
                "finalScore": adjusted_score,
            }
        )
        combine_warnings.append(
            f"Summary penalized {penalty} pts because {len(low_agents)} agents scored below 60."
        )

    timeline = combine_data.get("timeline", [])
    if len(timeline) < 6:
        combine_warnings.append(f"Timeline has {len(timeline)} entries (expected 6-10).")
    elif len(timeline) > 10:
        combine_data["timeline"] = timeline[:10]
        combine_warnings.append("Timeline trimmed to 10 entries.")

    recommendations = combine_data.get("recommendations", [])
    if len(recommendations) < 6:
        combine_warnings.append(
            f"Recommendations list has {len(recommendations)} entries (expected 6-8)."
        )
    elif len(recommendations) > 8:
        combine_data["recommendations"] = recommendations[:8]
        combine_warnings.append("Recommendations trimmed to 8 entries.")

    for rec in combine_data.get("recommendations", []):
        actions = rec.get("actions", [])
        if not (3 <= len(actions) <= 5):
            combine_warnings.append(
                f"Recommendation '{rec.get('title', '<untitled>')}' has {len(actions)} actions (expect 3-5)."
            )

    evaluation_report = {
        "meta": {
            "target": target,
            "context": context,
            "metadata": metadata,
            "model": "gemini-2.0-flash",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "graphOrder": graph_order,
        },
        "transcript": {
            "text": transcription_result["transcription"],
            "source": "user" if transcript_text else "elevenlabs",
            "word_analysis": transcription_result.get("word_analysis", []),
            "timestamps": transcription_result.get("timestamps", []),
            "loudness": transcription_result.get("loudness", []),
        },
        "audio_summary": audio_summary,
        "audio_analysis": audio_analysis,
        "deck": {
            "summary": deck_summary,
            "pages": deck_pages,
            "text": deck_text,
        },
        "agents": combined_agents,
        "agentWarnings": agent_warnings,
        "agentRaw": state["agent_raw"],
        "combine": combine_data,
        "combineRaw": combine_raw,
        "combineWarnings": combine_warnings,
        "summaryAdjustments": summary_adjustments,
    }

    return evaluation_report


def run_agent_workflow(job_id: str, job_payload: Dict[str, Any]) -> None:
    job_store.update_job_status(job_id, "running")
    try:
        report = execute_agent_workflow(job_payload)
        job_store.save_result(job_id, report)
        job_store.update_job_status(job_id, "completed")
    except Exception as exc:
        job_store.save_result(job_id, {"error": str(exc)})
        job_store.update_job_status(job_id, "failed", error=str(exc))
