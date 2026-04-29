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


def _failure_json_path(library_path: Path | str, failure_id: str) -> Path:
    return prompt_workflow_failure_dir(library_path) / f"{failure_id}.json"


def read_prompt_workflow_failure(library_path: Path | str, failure_id: str) -> dict[str, Any]:
    path = _failure_json_path(library_path, failure_id)
    if not path.is_file():
        raise KeyError(failure_id)
    return json.loads(path.read_text(encoding="utf-8"))


def _nested_value(payload: dict[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        current: Any = payload
        matched = True
        for part in path:
            if not isinstance(current, dict) or part not in current:
                matched = False
                break
            current = current[part]
        if matched and current not in (None, ""):
            return current
    return None


def summarize_prompt_workflow_failure(payload: dict[str, Any]) -> dict[str, Any]:
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    workflow = payload.get("workflow") if isinstance(payload.get("workflow"), dict) else None
    return {
        "id": payload.get("id"),
        "created_at": payload.get("created_at"),
        "operation": payload.get("operation"),
        "error_class": payload.get("error_class"),
        "error_message": payload.get("error_message"),
        "item_id": _nested_value(
            context,
            ("item_id",),
            ("item", "id"),
            ("template", "item_id"),
            ("session", "item_id"),
        ),
        "template_id": _nested_value(
            context,
            ("template_id",),
            ("template", "id"),
            ("session", "template_id"),
        ),
        "session_id": _nested_value(
            context,
            ("session_id",),
            ("session", "id"),
        ),
        "theme_keyword": _nested_value(context, ("theme_keyword",), ("session", "theme_keyword")),
        "requested_language": _nested_value(context, ("requested_language",), ("source_prompt", "language")),
        "response_status": workflow.get("response_status") if workflow else None,
    }


def list_prompt_workflow_failures(library_path: Path | str, limit: int = 50) -> list[dict[str, Any]]:
    directory = prompt_workflow_failure_dir(library_path)
    payloads: list[dict[str, Any]] = []
    for path in sorted(directory.glob("pwf_*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        payloads.append(summarize_prompt_workflow_failure(payload))
        if len(payloads) >= limit:
            break
    return payloads
