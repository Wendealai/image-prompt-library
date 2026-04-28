from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import traceback
from typing import Any
from uuid import uuid4

FAILURE_DIR = Path("_diagnostics") / "prompt-workflow-failures"
MAX_TEXT_LENGTH = 12000


def prompt_workflow_failure_dir(library_path: Path | str) -> Path:
    directory = Path(library_path) / FAILURE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _truncate_value(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) <= MAX_TEXT_LENGTH:
            return value
        omitted = len(value) - MAX_TEXT_LENGTH
        return f"{value[:MAX_TEXT_LENGTH]}\n...[truncated {omitted} chars]"
    if isinstance(value, list):
        return [_truncate_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _truncate_value(item) for key, item in value.items()}
    return value


def _workflow_metadata(exc: Exception) -> dict[str, Any] | None:
    metadata = {
        "operation": getattr(exc, "operation", None),
        "url": getattr(exc, "url", None),
        "request_payload": getattr(exc, "request_payload", None),
        "response_status": getattr(exc, "response_status", None),
        "response_text": getattr(exc, "response_text", None),
    }
    if all(value is None for value in metadata.values()):
        return None
    return metadata


def record_prompt_workflow_failure(
    *,
    library_path: Path | str,
    operation: str,
    exc: Exception,
    context: dict[str, Any] | None = None,
) -> tuple[str, Path]:
    failure_id = f"pwf_{uuid4().hex[:16]}"
    created_at = datetime.now(timezone.utc).isoformat()
    trace_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    payload: dict[str, Any] = {
        "id": failure_id,
        "created_at": created_at,
        "operation": operation,
        "error_class": type(exc).__name__,
        "error_message": str(exc),
        "context": _truncate_value(context or {}),
        "traceback": _truncate_value(trace_text),
    }

    workflow = _workflow_metadata(exc)
    if workflow is not None:
        payload["workflow"] = _truncate_value(workflow)

    output_path = prompt_workflow_failure_dir(library_path) / f"{failure_id}.json"
    output_path.write_text(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n", encoding="utf-8")
    return failure_id, output_path
