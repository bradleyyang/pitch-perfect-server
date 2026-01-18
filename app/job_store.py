import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(".data")
JOBS_DIR = BASE_DIR / "jobs"
RESULTS_DIR = BASE_DIR / "results"
UPLOADS_DIR = BASE_DIR / "uploads"


def _ensure_directories() -> None:
    for directory in (BASE_DIR, JOBS_DIR, RESULTS_DIR, UPLOADS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _result_path(job_id: str) -> Path:
    return RESULTS_DIR / f"{job_id}.json"


def create_job(job_id: str, target: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create or replace a job record."""
    _ensure_directories()

    job_payload = {
        "id": job_id,
        "target": target,
        "input": input_data,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }

    _write_json(_job_path(job_id), job_payload)
    return job_payload


def update_job(job_id: str, partial: Dict[str, Any]) -> Dict[str, Any]:
    """Merge partial data into an existing job record."""
    _ensure_directories()
    existing = get_job(job_id) or {"id": job_id}
    existing.update(partial)
    existing["updated_at"] = datetime.utcnow().isoformat() + "Z"
    _write_json(_job_path(job_id), existing)
    return existing


def update_job_status(job_id: str, status: str, error: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"status": status}
    if error:
        payload["error"] = error
    return update_job(job_id, payload)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    _ensure_directories()
    return _read_json(_job_path(job_id))


def save_result(job_id: str, result: Dict[str, Any]) -> None:
    _ensure_directories()
    _write_json(_result_path(job_id), result)


def get_result(job_id: str) -> Optional[Dict[str, Any]]:
    _ensure_directories()
    return _read_json(_result_path(job_id))


def persist_upload(job_id: str, filename: str, content: bytes, content_type: Optional[str] = None) -> Dict[str, Any]:
    _ensure_directories()
    safe_name = Path(filename).name
    destination = UPLOADS_DIR / f"{job_id}-{safe_name}"
    with destination.open("wb") as handle:
        handle.write(content)

    upload_record: Dict[str, Any] = {
        "job_id": job_id,
        "filename": safe_name,
        "path": str(destination),
    }
    if content_type:
        upload_record["content_type"] = content_type

    return upload_record
