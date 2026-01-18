import json
import os
import threading
import time
import uuid
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, List

from app.analysis import (
    extract_pdf_text,
    speech_to_text,
    track_loudness_deviation,
    gemini_client,
    FILLER_WORDS,
)


PROMPTS_DIR = Path(__file__).parent / "prompts"


class InMemoryJobStore:
    """Simple in-memory job tracker for the current process/session."""

    def __init__(self) -> None:
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_job(self) -> str:
        job_id = uuid.uuid4().hex
        now = time.time()
        job = {
            "id": job_id,
            "status": "pending",
            "createdAt": now,
            "updatedAt": now,
            "warnings": [],
            "logs": [],
            "result": None,
            "error": None,
            "paths": {},
        }
        with self._lock:
            self.jobs[job_id] = job
        return job_id

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self.jobs.get(job_id)
            return dict(job) if job else None

    def _update(self, job_id: str, **updates: Any) -> None:
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            job.update(updates)
            job["updatedAt"] = time.time()

    def mark_running(self, job_id: str) -> None:
        self._update(job_id, status="running", startedAt=time.time())

    def mark_complete(self, job_id: str, result: Dict[str, Any], warnings: list, logs: list) -> None:
        self._update(job_id, status="completed", completedAt=time.time(), result=result, warnings=warnings, logs=logs)

    def mark_failed(self, job_id: str, error: str, warnings: list, logs: list) -> None:
        self._update(job_id, status="failed", completedAt=time.time(), error=error, warnings=warnings, logs=logs)

    def attach_paths(self, job_id: str, paths: Dict[str, str]) -> None:
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            job["paths"].update(paths)
            job["updatedAt"] = time.time()


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


def _safe_json_parse(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        return {"raw": text.strip()}


def _run_gemini(prompt_file: str, context: str, model: str = "gemini-2.0-flash") -> Dict[str, Any]:
    prompt = _load_prompt(prompt_file)
    contents = f"{prompt}\n\nContext:\n{context}"
    response = gemini_client.models.generate_content(model=model, contents=contents)
    return _safe_json_parse(getattr(response, "text", "") or "")


def _build_warning(message: str) -> str:
    return message


def _combine_report(parts: Dict[str, Any], warnings: list, telemetry: Dict[str, Any]) -> Dict[str, Any]:
    # Compose a brief summary for the combine prompt
    combined_context = json.dumps({k: v for k, v in parts.items() if v}, indent=2)
    combine_result = None
    try:
        combine_result = _run_gemini("combine-agent.txt", combined_context)
    except Exception as exc:  # pragma: no cover - runtime protection
        warnings.append(_build_warning(f"Combine stage failed: {exc}"))
    overall_score = telemetry.get("overallScore")
    if not overall_score and isinstance(combine_result, dict):
        overall_score = combine_result.get("overallScore")
    if overall_score is None:
        overall_score = 0
    audio_entry = parts.get("audio") or {}
    if isinstance(audio_entry, dict):
        audio_entry = dict(audio_entry)
        audio_entry.setdefault("metrics", telemetry.get("metrics") or {})

    return {
        "version": "1.0",
        "summary": combine_result or {},
        "deck": parts.get("deck"),
        "transcript": parts.get("transcript_quality"),
        "delivery": parts.get("delivery"),
        "speechContent": parts.get("speech_content"),
        "audio": audio_entry,
        "recommendations": combine_result.get("recommendations") if isinstance(combine_result, dict) else [],
        "voiceNarrations": combine_result.get("voiceScripts") if isinstance(combine_result, dict) else [],
        "warnings": warnings,
        "overallScore": overall_score,
        "metrics": telemetry.get("metrics") or {},
        "transcription": telemetry.get("transcription") or "",
        "word_analysis": telemetry.get("word_analysis") or [],
        "timestamps": telemetry.get("timestamps") or [],
        "loudness": telemetry.get("loudness") or [],
        "meta": {"generatedAt": time.time(), "model": "gemini-2.0-flash", "target": "pitch-perfect"},
    }


def process_job(
    job_store: InMemoryJobStore,
    job_id: str,
    deck_path: Optional[str],
    transcript_text: Optional[str],
    media_path: Optional[str],
) -> None:
    warnings: list = []
    logs: list = []
    job_store.mark_running(job_id)

    parts: Dict[str, Any] = {
        "deck": None,
        "transcript_quality": None,
        "delivery": None,
        "speech_content": None,
        "audio": None,
    }

    telemetry: Dict[str, Any] = {
        "overallScore": None,
        "metrics": {},
        "transcription": "",
        "word_analysis": [],
        "timestamps": [],
        "loudness": [],
    }

    try:
        deck_text = None
        stt_result = None
        loudness_series: List[List[float]] = []

        if transcript_text:
            telemetry["transcription"] = transcript_text

        if deck_path:
            try:
                deck_extracted = extract_pdf_text(deck_path)
                deck_text = json.dumps(deck_extracted, indent=2)
                parts["deck"] = _run_gemini("deck-agent.txt", deck_text)
            except Exception as exc:
                warnings.append(_build_warning(f"Deck analysis failed: {exc}"))
                logs.append(f"deck_error: {exc}")

        if not transcript_text and media_path:
            try:
                stt_result = speech_to_text(media_path)
                transcript_text = stt_result.get("transcription")
                telemetry["transcription"] = stt_result.get("transcription") or ""
                telemetry["word_analysis"] = stt_result.get("word_analysis") or []
                telemetry["timestamps"] = stt_result.get("timestamps") or []
                telemetry["loudness"] = stt_result.get("loudness") or []
            except Exception as exc:
                warnings.append(_build_warning(f"ElevenLabs STT failed: {exc}"))
                logs.append(f"stt_error: {exc}")

        if transcript_text:
            context_text = transcript_text[:8000]
            try:
                parts["delivery"] = _run_gemini("text-agent.txt", context_text)
            except Exception as exc:
                warnings.append(_build_warning(f"Delivery analysis failed: {exc}"))
                logs.append(f"delivery_error: {exc}")
            try:
                parts["speech_content"] = _run_gemini("speech-content-agent.txt", context_text)
            except Exception as exc:
                warnings.append(_build_warning(f"Speech content analysis failed: {exc}"))
                logs.append(f"speech_content_error: {exc}")
            try:
                parts["transcript_quality"] = _run_gemini("transcription-agent.txt", context_text)
            except Exception as exc:
                warnings.append(_build_warning(f"Transcript quality analysis failed: {exc}"))
                logs.append(f"transcription_error: {exc}")
        else:
            warnings.append(_build_warning("No transcript provided or recovered; skipping text-based analyses."))

        if media_path:
            try:
                # Use existing loudness tracker for debugging metrics
                loudness_series = track_loudness_deviation(media_path)
                audio_context = {
                    "transcript": transcript_text or "",
                    "loudnessSamples": loudness_series[:200],
                    "sttSummary": stt_result if stt_result else {},
                }
                parts["audio"] = _run_gemini("audio-agent.txt", json.dumps(audio_context, indent=2))
                telemetry["loudness"] = telemetry["loudness"] or loudness_series
            except Exception as exc:
                warnings.append(_build_warning(f"Audio analysis failed: {exc}"))
                logs.append(f"audio_error: {exc}")

        telemetry["metrics"] = telemetry["metrics"] or _derive_metrics(
            telemetry.get("word_analysis") or [],
            telemetry.get("loudness") or loudness_series,
            telemetry.get("timestamps") or [],
        )
        telemetry["overallScore"] = telemetry["metrics"].get("overallScore")

        report = _combine_report(parts, warnings, telemetry)
        job_store.mark_complete(job_id, report, warnings, logs)
    except Exception as exc:  # pragma: no cover - top-level protection
        job_store.mark_failed(job_id, str(exc), warnings, logs)
    finally:
        # Keep temp artifacts for this process for debugging; caller may clean up if desired.
        pass


def persist_upload(upload, dest_dir: str, filename: str) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    with open(dest_path, "wb") as f:
        f.write(upload)
    return dest_path


def allocate_job_space(job_id: str) -> str:
    return tempfile.mkdtemp(prefix=f"job_{job_id}_")


def _derive_metrics(word_analysis: List[Dict[str, Any]], loudness: List[List[float]], timestamps: List[List[float]]) -> Dict[str, float]:
    """Best-effort metrics for playback/visual widgets; fall back to empty values."""
    metrics: Dict[str, float] = {}
    if word_analysis:
        avg_spm = sum(w.get("syllables_per_minute", 0) for w in word_analysis) / max(len(word_analysis), 1)
        metrics["paceWpm"] = round(avg_spm / 1.6, 2)  # rough syllables->words conversion
        filler_count = sum(1 for w in word_analysis if isinstance(w.get("word"), str) and w["word"].lower() in FILLER_WORDS)
        duration_sec = 0.0
        if timestamps:
            duration_sec = max(t[0] for t in timestamps if t) or 0.0
        metrics["fillerWordsPerMin"] = round(filler_count / (duration_sec / 60), 2) if duration_sec > 0 else 0.0
    if loudness:
        db_vals = [point[1] for point in loudness if len(point) > 1]
        if db_vals:
            metrics["avgVolumeDb"] = round(sum(db_vals) / len(db_vals), 2)
            silence_threshold = -50
            silence_fraction = sum(1 for v in db_vals if v < silence_threshold) / len(db_vals)
            metrics["silenceRatio"] = round(silence_fraction, 3)
    # Ensure keys exist even if not computed
    metrics.setdefault("paceWpm", 0.0)
    metrics.setdefault("fillerWordsPerMin", 0.0)
    metrics.setdefault("silenceRatio", 0.0)
    metrics.setdefault("avgVolumeDb", 0.0)
    return metrics
