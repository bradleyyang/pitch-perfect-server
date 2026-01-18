from typing import Dict

import pytest

from app import agent_workflow


def _fake_agent_response(name: str, _: Dict[str, object]):
    if name == "combine":
        combine_parsed = {
            "summary": {
                "overallScore": 90,
                "headline": "Fake Summary",
                "highlights": [],
                "risks": [],
            },
            "timeline": [{"timestamp": f"{i}:00"} for i in range(12)],
            "recommendations": [
                {"title": f"Rec {i}", "actions": ["a", "b", "c", "d"]}
                for i in range(9)
            ],
            "voiceScripts": [
                {"persona": "encouraging", "tone": "warm", "script": "Keep going."}
            ],
        }
        return {"parsed": combine_parsed, "raw": "combine_raw", "warnings": []}

    score_map = {
        "deck": 70,
        "text": 68,
        "speech_content": 55,
        "audio": 60,
        "voice": 72,
        "transcription": 65,
    }
    return {
        "parsed": {"overallScore": score_map.get(name, 65)},
        "raw": f"{name}_raw",
        "warnings": [],
    }


def test_combine_rules_trim_and_penalty(monkeypatch):
    monkeypatch.setattr(agent_workflow, "_call_agent", _fake_agent_response)

    payload = {
        "target": "Test",
        "context": "Test context",
        "metadata": {},
        "transcript": "Hello, world!",
        "transcript_source": "user",
        "deck": None,
        "media": None,
    }

    report = agent_workflow.execute_agent_workflow(payload)

    assert report["combineRaw"] == "combine_raw"
    combine = report["combine"]
    assert len(combine["timeline"]) == 10, "Timeline should be trimmed to 10 entries"
    assert len(combine["recommendations"]) == 8, "Recommendations should be trimmed to 8"
    assert combine["voiceScripts"][0]["persona"] == "encouraging"

    warnings = report.get("combineWarnings", [])
    assert any("Timeline trimmed" in msg for msg in warnings)
    assert any("Recommendations trimmed" in msg for msg in warnings)
    assert any("lowered by" in msg for msg in warnings)

    adjustments = report.get("summaryAdjustments", [])
    assert adjustments, "Summary adjustments should exist when weighted average is lower"
    assert adjustments[0]["penalty"] > 0
