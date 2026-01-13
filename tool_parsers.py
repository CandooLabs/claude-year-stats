"""Additional AI tool parsers for year review."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_jsonl(filepath: Path) -> List[Dict]:
    """Parse JSONL file into list of dicts."""
    entries = []
    if not filepath.exists():
        return entries
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass
    return entries


def parse_timestamp(ts: Any) -> Optional[datetime]:
    """Parse various timestamp formats."""
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            if ts > 1e12:
                return datetime.fromtimestamp(ts / 1000)
            return datetime.fromtimestamp(ts)
        if isinstance(ts, str):
            for fmt in [
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
            ]:
                try:
                    return datetime.strptime(ts, fmt)
                except ValueError:
                    continue
    except Exception:
        pass
    return None


def analyze_codex_dir(codex_dir: Path, source_name: str = "local") -> Dict:
    """Analyze OpenAI Codex CLI usage data from sessions/*.jsonl."""
    result = {
        "source": source_name,
        "tool": "codex",
        "timestamps": [],
        "total_sessions": 0,
        "total_messages": 0,
        "model_usage": {},
        "projects": [],
        "longest_session": None,
    }

    sessions_dir = codex_dir / "sessions"
    if not sessions_dir.exists():
        return result

    session_files = list(sessions_dir.glob("**/*.jsonl"))
    result["total_sessions"] = len(session_files)

    for session_file in session_files:
        last_usage = None
        session_model = "unknown"

        for entry in parse_jsonl(session_file):
            ts = parse_timestamp(entry.get("timestamp"))
            entry_type = entry.get("type", "")

            if ts:
                result["timestamps"].append(
                    {"ts": ts, "source": source_name, "tool": "codex"}
                )

            # Get model from turn_context
            if entry_type == "turn_context":
                payload = entry.get("payload", {})
                model = payload.get("model", session_model)
                if model:
                    session_model = model

            # Get usage from event_msg
            if entry_type == "event_msg":
                payload = entry.get("payload", {})
                msg_type = payload.get("type")
                if msg_type == "user_message":
                    result["total_messages"] += 1
                elif msg_type == "token_count":
                    info = payload.get("info", {})
                    if info:
                        last_usage = info.get("last_token_usage", {})

        # Accumulate from last usage in session
        if last_usage and session_model:
            if session_model not in result["model_usage"]:
                result["model_usage"][session_model] = {
                    "input": 0,
                    "output": 0,
                    "cache_read": 0,
                    "cache_creation": 0,
                    "total": 0,
                }

            inp = last_usage.get("input_" + "tokens", 0)
            out = last_usage.get("output_" + "tokens", 0)
            cached = last_usage.get("cached_input_" + "tokens", 0)
            reasoning = last_usage.get("reasoning_output_" + "tokens", 0)

            result["model_usage"][session_model]["input"] += inp
            result["model_usage"][session_model]["output"] += out
            result["model_usage"][session_model]["cache_read"] += cached
            result["model_usage"][session_model]["total"] += inp + out + reasoning

    return result


def analyze_opencode_dir(opencode_dir: Path, source_name: str = "local") -> Dict:
    """Analyze OpenCode usage data from logs."""
    result = {
        "source": source_name,
        "tool": "opencode",
        "timestamps": [],
        "total_sessions": 0,
        "total_messages": 0,
        "model_usage": {},
        "projects": [],
        "longest_session": None,
    }

    log_dir = opencode_dir / "log"
    if log_dir.exists():
        for log_file in log_dir.glob("*.log"):
            try:
                name = log_file.stem
                if "T" in name:
                    date_part = name.split("T")[0]
                    ts = parse_timestamp(date_part + "T00:00:00Z")
                    if ts:
                        result["timestamps"].append(
                            {"ts": ts, "source": source_name, "tool": "opencode"}
                        )
                        result["total_sessions"] += 1
            except Exception:
                continue

    storage_dir = opencode_dir / "storage" / "project"
    if storage_dir.exists():
        project_files = list(storage_dir.glob("*.json"))
        result["projects"] = [{"name": f.stem, "sessions": 1} for f in project_files]

    return result
