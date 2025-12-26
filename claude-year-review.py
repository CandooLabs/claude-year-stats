#!/usr/bin/env python3
"""
Claude Code Year in Review - Analyzes local Claude Code usage data.

Usage:
  python3 claude-year-review.py                           # Local only
  python3 claude-year-review.py --remote user@host        # Include remote
  python3 claude-year-review.py --remote h1 --remote h2   # Multiple remotes
  python3 claude-year-review.py --remote-only user@host   # Remote only, skip local
  python3 claude-year-review.py --data-path /path/.claude # Include pre-fetched data
  python3 claude-year-review.py --merge-sources "a=b"     # Merge source 'a' into 'b'
  python3 claude-year-review.py --json                    # Output as JSON
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def run_cmd(cmd: List[str], timeout: int = 60) -> Tuple[bool, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def fetch_remote_data(remote: str, temp_dir: Path) -> Optional[Path]:
    remote_dir = temp_dir / remote.replace("@", "_at_").replace(".", "_").replace(
        ":", "_"
    )
    remote_dir.mkdir(parents=True, exist_ok=True)

    print(f"  Fetching data from {remote}...")

    success, output = run_cmd(
        [
            "rsync",
            "-avz",
            f"{remote}:.claude/",
            str(remote_dir) + "/",
        ],
        timeout=120,
    )

    if not success:
        print(f"  Warning: Failed to fetch from {remote}")
        print(f"    {output[:200]}")
        return None

    if not any(remote_dir.iterdir()):
        print(f"  Warning: No data found on {remote}")
        return None

    print(f"  Fetched data from {remote}")
    return remote_dir


def find_claude_data_dirs(include_local: bool = True) -> List[Path]:
    dirs = []

    if include_local:
        home = Path.home()
        main_claude = home / ".claude"
        if main_claude.exists():
            dirs.append(main_claude)

    return dirs


def parse_jsonl(filepath: Path) -> List[Dict]:
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


MACHINE_COLORS = [
    "#ff6b35",
    "#4ecdc4",
    "#a855f7",
    "#22c55e",
    "#f43f5e",
    "#3b82f6",
    "#eab308",
    "#ec4899",
]


def analyze_claude_dir(claude_dir: Path, source_name: str = "local") -> Dict:
    data = {
        "source": source_name,
        "timestamps": [],
        "total_sessions": 0,
        "total_messages": 0,
        "model_usage": {},
        "projects": [],
        "longest_session": None,
    }

    history_file = claude_dir / "history.jsonl"
    for entry in parse_jsonl(history_file):
        ts = parse_timestamp(entry.get("timestamp"))
        if ts:
            data["timestamps"].append({"ts": ts, "source": source_name})

    stats_file = claude_dir / "stats-cache.json"
    if stats_file.exists():
        try:
            with open(stats_file, "r") as f:
                stats = json.load(f)

            data["total_sessions"] = stats.get("totalSessions", 0)
            data["total_messages"] = stats.get("totalMessages", 0)

            longest = stats.get("longestSession", {})
            if longest:
                data["longest_session"] = {
                    "duration_ms": longest.get("duration", 0),
                    "messages": longest.get("messageCount", 0),
                }
        except Exception:
            pass

    transcripts_dir = claude_dir / "transcripts"
    if transcripts_dir.exists():
        for transcript_file in transcripts_dir.glob("*.jsonl"):
            for entry in parse_jsonl(transcript_file):
                ts = parse_timestamp(entry.get("timestamp"))
                if ts:
                    data["timestamps"].append({"ts": ts, "source": source_name})

    projects_dir = claude_dir / "projects"
    if projects_dir.exists():
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir():
                project_name = project_dir.name.replace("-", "/").lstrip("/")
                session_files = list(project_dir.glob("*.jsonl"))
                data["projects"].append(
                    {
                        "name": project_name,
                        "sessions": len(
                            [
                                f
                                for f in session_files
                                if not f.name.startswith("agent-")
                            ]
                        ),
                    }
                )

                # Always parse session files for accurate token counts
                # (stats-cache.json is undocumented and may be stale/incomplete)
                for session_file in session_files:
                    for entry in parse_jsonl(session_file):
                        msg = entry.get("message", {})
                        usage = msg.get("usage", {})
                        model = msg.get("model", "unknown")

                        if usage:
                            input_t = usage.get("input_tokens", 0)
                            output_t = usage.get("output_tokens", 0)
                            cache_read = usage.get("cache_read_input_tokens", 0)
                            cache_create = usage.get("cache_creation_input_tokens", 0)

                            if model not in data["model_usage"]:
                                data["model_usage"][model] = {
                                    "input": 0,
                                    "output": 0,
                                    "cache_read": 0,
                                    "cache_creation": 0,
                                    "total": 0,
                                }

                            data["model_usage"][model]["input"] += input_t
                            data["model_usage"][model]["output"] += output_t
                            data["model_usage"][model]["cache_read"] += cache_read
                            data["model_usage"][model]["cache_creation"] += cache_create
                            data["model_usage"][model]["total"] += (
                                input_t + output_t + cache_read + cache_create
                            )

    return data


def aggregate_data(
    sources: List[Dict], merge_mapping: Optional[Dict[str, str]] = None
) -> Dict:
    if merge_mapping is None:
        merge_mapping = {}

    all_timestamps = []
    total_sessions = 0
    total_messages = 0
    model_usage = {}
    all_projects = []
    longest_session = None
    source_names_seen = set()
    source_names = []
    source_colors = {}
    per_source_stats = {}

    for idx, source in enumerate(sources):
        raw_source_name = source.get("source", "unknown")
        source_name = merge_mapping.get(raw_source_name, raw_source_name)

        if source_name not in source_names_seen:
            source_names_seen.add(source_name)
            source_names.append(source_name)
            source_colors[source_name] = MACHINE_COLORS[
                len(source_names) - 1 % len(MACHINE_COLORS)
            ]

        timestamps_with_renamed_source = []
        for ts_entry in source.get("timestamps", []):
            new_entry = ts_entry.copy()
            new_entry["source"] = source_name
            timestamps_with_renamed_source.append(new_entry)
        all_timestamps.extend(timestamps_with_renamed_source)

        total_sessions += source.get("total_sessions", 0)
        total_messages += source.get("total_messages", 0)

        source_tokens = sum(
            m.get("total", 0) for m in source.get("model_usage", {}).values()
        )
        source_ts = [t["ts"] for t in source.get("timestamps", [])]

        if source_name not in per_source_stats:
            per_source_stats[source_name] = {
                "tokens": 0,
                "sessions": 0,
                "messages": 0,
                "days_set": set(),
                "events": 0,
            }

        per_source_stats[source_name]["tokens"] += source_tokens
        per_source_stats[source_name]["sessions"] += source.get("total_sessions", 0)
        per_source_stats[source_name]["messages"] += source.get("total_messages", 0)
        per_source_stats[source_name]["events"] += len(source.get("timestamps", []))
        per_source_stats[source_name]["days_set"].update(t.date() for t in source_ts)

        for model, usage in source.get("model_usage", {}).items():
            if model not in model_usage:
                model_usage[model] = usage.copy()
            else:
                for key in usage:
                    if isinstance(usage[key], (int, float)):
                        model_usage[model][key] = (
                            model_usage[model].get(key, 0) + usage[key]
                        )

        all_projects.extend(source.get("projects", []))

        ls = source.get("longest_session")
        if ls:
            if longest_session is None or ls.get(
                "duration_ms", 0
            ) > longest_session.get("duration_ms", 0):
                longest_session = ls

    all_timestamps.sort(key=lambda x: x["ts"])
    total_tokens = sum(m.get("total", 0) for m in model_usage.values())

    for stats in per_source_stats.values():
        stats["days"] = len(stats.pop("days_set"))

    date_range = None
    if all_timestamps:
        date_range = (all_timestamps[0]["ts"], all_timestamps[-1]["ts"])

    just_timestamps = [t["ts"] for t in all_timestamps]
    streaks = calculate_streaks(just_timestamps)

    return {
        "sources": source_names,
        "source_colors": source_colors,
        "per_source_stats": per_source_stats,
        "date_range": date_range,
        "all_timestamps": all_timestamps,
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "total_tokens": total_tokens,
        "model_usage": model_usage,
        "projects": all_projects,
        "streaks": streaks,
        "longest_session": longest_session,
    }


def calculate_streaks(timestamps: List[datetime]) -> Dict:
    if not timestamps:
        return {"current": 0, "longest": 0, "total_days": 0}

    dates = sorted(set(ts.date() for ts in timestamps))

    if not dates:
        return {"current": 0, "longest": 0, "total_days": 0}

    longest_streak = 1
    current_streak = 1

    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            current_streak += 1
            longest_streak = max(longest_streak, current_streak)
        else:
            current_streak = 1

    today = datetime.now().date()
    if dates[-1] >= today - timedelta(days=1):
        current_streak = 1
        for i in range(len(dates) - 1, 0, -1):
            if (dates[i] - dates[i - 1]).days == 1:
                current_streak += 1
            else:
                break
    else:
        current_streak = 0

    return {
        "current": current_streak,
        "longest": longest_streak,
        "total_days": len(dates),
    }


def format_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    elif n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def generate_html_report(data: Dict) -> str:
    all_timestamps = data.get("all_timestamps", [])
    sources = data.get("sources", ["local"])
    source_colors = data.get("source_colors", {"local": MACHINE_COLORS[0]})

    first_date = None
    if data.get("date_range"):
        first_date = data["date_range"][0]

    days_ago = 0
    if first_date:
        days_ago = (datetime.now() - first_date).days

    active_dates = set()
    date_activity = defaultdict(int)
    date_sources = defaultdict(set)
    for item in all_timestamps:
        ts = item["ts"]
        source = item["source"]
        d = ts.date()
        active_dates.add(d)
        date_activity[d] += 1
        date_sources[d].add(source)

    max_activity = max(date_activity.values()) if date_activity else 1

    models = data.get("model_usage", {})
    sorted_models = sorted(
        models.items(), key=lambda x: x[1].get("total", 0), reverse=True
    )

    total_tokens = data.get("total_tokens", 0)
    total_sessions = data.get("total_sessions", 0)
    streaks = data.get("streaks", {})

    weekly_tokens = defaultdict(int)
    weekly_sources = defaultdict(set)
    if all_timestamps:
        year_start = datetime(datetime.now().year, 1, 1).date()
        for item in all_timestamps:
            ts = item["ts"]
            source = item["source"]
            week_num = (ts.date() - year_start).days // 7 + 1
            if 1 <= week_num <= 52:
                weekly_tokens[week_num] += 1
                weekly_sources[week_num].add(source)

    year = datetime.now().year

    calendar_html = ""
    months = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]

    for month_idx, month_name in enumerate(months, 1):
        month_start = datetime(year, month_idx, 1).date()
        if month_idx == 12:
            month_end = datetime(year + 1, 1, 1).date() - timedelta(days=1)
        else:
            month_end = datetime(year, month_idx + 1, 1).date() - timedelta(days=1)

        days_html = ""
        current = month_start
        while current <= month_end:
            activity = date_activity.get(current, 0)
            day_sources = date_sources.get(current, set())

            if activity == 0:
                color = "var(--dot-inactive)"
            elif len(day_sources) == 1:
                source = list(day_sources)[0]
                color = source_colors.get(source, MACHINE_COLORS[0])
            else:
                color = (
                    "linear-gradient(135deg, "
                    + ", ".join(
                        source_colors.get(s, MACHINE_COLORS[0])
                        for s in sorted(day_sources)
                    )
                    + ")"
                )

            sources_str = ", ".join(sorted(day_sources)) if day_sources else "none"
            days_html += f'<div class="dot" style="background: {color};" title="{current}: {activity} events ({sources_str})"></div>'
            current += timedelta(days=1)

        calendar_html += f"""
        <div class="month">
            <div class="month-label">{month_name}</div>
            <div class="month-dots">{days_html}</div>
        </div>
        """

    weeks_html = ""
    max_weeks = 52
    weekly_token_totals = defaultdict(int)
    tokens_per_event = total_tokens / len(all_timestamps) if all_timestamps else 0
    for week in range(1, max_weeks + 1):
        weekly_token_totals[week] = int(weekly_tokens.get(week, 0) * tokens_per_event)

    max_week_tokens = (
        max(weekly_token_totals.values()) if any(weekly_token_totals.values()) else 1
    )

    for week in range(1, max_weeks + 1):
        tokens = weekly_token_totals.get(week, 0)
        opacity = 0.15 if tokens == 0 else 0.3 + (tokens / max_week_tokens) * 0.7
        token_display = format_number(tokens) if tokens > 0 else ""
        highlight = "highlight" if tokens > 0 else ""
        weeks_html += f"""
        <div class="week {highlight}" style="opacity: {opacity};">
            <div class="week-label">Week {week}</div>
            <div class="week-tokens">{token_display}</div>
        </div>
        """

    models_html = ""
    for idx, (model_name, usage) in enumerate(sorted_models[:5], 1):
        display_name = (
            model_name.replace("claude-", "Claude ").replace("-", " ").title()
        )
        if len(display_name) > 25:
            display_name = display_name[:22] + "..."
        models_html += f'<div class="model-item"><span class="model-rank">{idx}</span> <span class="model-name">{display_name}</span></div>'

    if not models_html:
        models_html = '<div class="model-item"><span class="model-rank">-</span> <span class="model-name">No data</span></div>'

    mini_calendar_html = ""
    for month_idx in range(1, 13):
        month_start = datetime(year, month_idx, 1).date()
        if month_idx == 12:
            month_end = datetime(year + 1, 1, 1).date() - timedelta(days=1)
        else:
            month_end = datetime(year, month_idx + 1, 1).date() - timedelta(days=1)

        dots_html = ""
        current = month_start
        while current <= month_end:
            activity = date_activity.get(current, 0)
            day_sources = date_sources.get(current, set())

            if activity == 0:
                color = "var(--dot-inactive)"
            elif len(day_sources) == 1:
                source = list(day_sources)[0]
                color = source_colors.get(source, MACHINE_COLORS[0])
            else:
                color = source_colors.get(sorted(day_sources)[0], MACHINE_COLORS[0])

            dots_html += f'<div class="mini-dot" style="background: {color};"></div>'
            current += timedelta(days=1)

        mini_calendar_html += f'<div class="mini-month">{dots_html}</div>'

    sources_text = (
        ", ".join(sources) if len(sources) <= 3 else f"{len(sources)} machines"
    )

    legend_html = ""
    for source in sources:
        color = source_colors.get(source, MACHINE_COLORS[0])
        display_name = source if len(source) <= 20 else source[:17] + "..."
        legend_html += f'<div class="legend-item"><div class="legend-dot" style="background: {color};"></div><span>{display_name}</span></div>'

    per_source_stats = data.get("per_source_stats", {})
    host_stats_html = ""
    for source in sources:
        color = source_colors.get(source, MACHINE_COLORS[0])
        stats = per_source_stats.get(source, {})
        display_name = source if len(source) <= 25 else source[:22] + "..."
        host_stats_html += f"""
        <div class="host-stat-card" style="border-left: 4px solid {color};">
            <div class="host-name" style="color: {color};">{display_name}</div>
            <div class="host-stats-grid">
                <div><span class="host-stat-value">{format_number(stats.get("tokens", 0))}</span><span class="host-stat-label">tokens</span></div>
                <div><span class="host-stat-value">{stats.get("days", 0)}</span><span class="host-stat-label">days</span></div>
                <div><span class="host-stat-value">{stats.get("sessions", 0)}</span><span class="host-stat-label">sessions</span></div>
                <div><span class="host-stat-value">{stats.get("events", 0)}</span><span class="host-stat-label">events</span></div>
            </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Claude Code - Year in Review {year}</title>
    <style>
        :root {{
            --bg-dark: #1a1a1a;
            --bg-card: #252525;
            --text-primary: #ffffff;
            --text-secondary: #888888;
            --text-dim: #555555;
            --dot-inactive: #333333;
            --dot-low: #4a4a4a;
            --dot-med: #888888;
            --dot-high: #ff6b35;
            --accent: #ff6b35;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-dark);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 40px 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .section {{
            margin-bottom: 80px;
        }}
        
        .section-title {{
            font-size: 32px;
            font-weight: 300;
            margin-bottom: 40px;
            line-height: 1.3;
        }}
        
        .sources-badge {{
            display: inline-block;
            background: var(--bg-card);
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 14px;
            color: var(--text-secondary);
            margin-bottom: 20px;
        }}
        
        .legend {{
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            margin-bottom: 40px;
        }}
        
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
            color: var(--text-secondary);
        }}
        
        .legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}
        
        .host-stats-section {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 16px;
            margin-bottom: 40px;
        }}
        
        .host-stat-card {{
            background: var(--bg-card);
            padding: 20px;
            border-radius: 8px;
        }}
        
        .host-name {{
            font-size: 16px;
            font-weight: 500;
            margin-bottom: 16px;
        }}
        
        .host-stats-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }}
        
        .host-stat-value {{
            font-size: 24px;
            font-weight: 300;
            display: block;
        }}
        
        .host-stat-label {{
            font-size: 12px;
            color: var(--text-secondary);
        }}
        
        .stats-row {{
            display: flex;
            gap: 60px;
            margin-bottom: 40px;
        }}
        
        .stat {{
            display: flex;
            flex-direction: column;
        }}
        
        .stat-label {{
            font-size: 14px;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }}
        
        .stat-value {{
            font-size: 48px;
            font-weight: 300;
        }}
        
        .calendar {{
            display: flex;
            gap: 8px;
            overflow-x: auto;
            padding-bottom: 20px;
        }}
        
        .month {{
            display: flex;
            flex-direction: column;
            min-width: 80px;
        }}
        
        .month-label {{
            font-size: 14px;
            color: var(--text-secondary);
            margin-bottom: 12px;
        }}
        
        .month-dots {{
            display: flex;
            flex-direction: column;
            gap: 3px;
        }}
        
        .dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            transition: transform 0.2s;
        }}
        
        .dot:hover {{
            transform: scale(1.5);
        }}
        
        .weeks-grid {{
            display: grid;
            grid-template-columns: repeat(12, 1fr);
            gap: 12px;
        }}
        
        .week {{
            padding: 16px;
            background: var(--bg-card);
            border-radius: 4px;
            min-height: 80px;
        }}
        
        .week.highlight {{
            background: var(--bg-card);
        }}
        
        .week-label {{
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }}
        
        .week-tokens {{
            font-size: 14px;
            color: var(--text-primary);
        }}
        
        .summary-card {{
            background: var(--bg-card);
            border-radius: 16px;
            padding: 40px;
            max-width: 600px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 40px;
        }}
        
        .card-left {{
            display: flex;
            flex-direction: column;
            gap: 24px;
        }}
        
        .card-right {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}
        
        .joined {{
            color: var(--text-secondary);
            font-size: 14px;
        }}
        
        .models-section h3 {{
            font-size: 14px;
            color: var(--text-secondary);
            font-weight: normal;
            margin-bottom: 12px;
        }}
        
        .model-item {{
            font-size: 18px;
            margin-bottom: 4px;
        }}
        
        .model-rank {{
            color: var(--text-secondary);
            margin-right: 8px;
        }}
        
        .card-stats {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        
        .card-stat-label {{
            font-size: 12px;
            color: var(--text-secondary);
        }}
        
        .card-stat-value {{
            font-size: 28px;
            font-weight: 300;
        }}
        
        .mini-calendar {{
            display: grid;
            grid-template-columns: repeat(12, 1fr);
            gap: 2px;
        }}
        
        .mini-month {{
            display: flex;
            flex-direction: column;
            gap: 1px;
        }}
        
        .mini-dot {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
        }}
        
        .branding {{
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-secondary);
            font-size: 14px;
            margin-top: 20px;
        }}
        
        .logo {{
            width: 24px;
            height: 24px;
        }}
        
        @media (max-width: 768px) {{
            .weeks-grid {{
                grid-template-columns: repeat(4, 1fr);
            }}
            
            .summary-card {{
                grid-template-columns: 1fr;
            }}
            
            .stats-row {{
                flex-direction: column;
                gap: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="sources-badge">Data from: {sources_text}</div>
        <div class="legend">{legend_html}</div>
        
        <div class="host-stats-section">
            {host_stats_html}
        </div>
        
        <section class="section">
            <h1 class="section-title">Agents run on tokens.<br>Millions of them were yours.</h1>
            <div class="stats-row">
                <div class="stat">
                    <div class="stat-label">Tokens Used</div>
                    <div class="stat-value">{total_tokens:,}</div>
                </div>
            </div>
            <div class="weeks-grid">
                {weeks_html}
            </div>
        </section>
        
        <section class="section">
            <h1 class="section-title">You got started building with Claude Code.</h1>
            <div class="stats-row">
                <div class="stat">
                    <div class="stat-label">Days Used</div>
                    <div class="stat-value">{streaks.get("total_days", 0)}</div>
                </div>
                <div class="stat">
                    <div class="stat-label">Longest Streak</div>
                    <div class="stat-value">{streaks.get("longest", 0)}d</div>
                </div>
            </div>
            <div class="calendar">
                {calendar_html}
            </div>
        </section>
        
        <section class="section">
            <div class="summary-card">
                <div class="card-left">
                    <div class="joined">Started {days_ago} Days Ago</div>
                    
                    <div class="models-section">
                        <h3>Models</h3>
                        {models_html}
                    </div>
                    
                    <div class="card-stats">
                        <div>
                            <div class="card-stat-label">Sessions</div>
                            <div class="card-stat-value">{total_sessions}</div>
                        </div>
                        <div>
                            <div class="card-stat-label">Messages</div>
                            <div class="card-stat-value">{data.get("total_messages", 0)}</div>
                        </div>
                        <div>
                            <div class="card-stat-label">Tokens</div>
                            <div class="card-stat-value">{format_number(total_tokens)}</div>
                        </div>
                        <div>
                            <div class="card-stat-label">Streak</div>
                            <div class="card-stat-value">{streaks.get("longest", 0)}d</div>
                        </div>
                    </div>
                    
                    <div class="branding">
                        <svg class="logo" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 2L2 7v10l10 5 10-5V7L12 2zm0 2.5L18.5 7 12 9.5 5.5 7 12 4.5zM4 8.5l7 3.5v7.5l-7-3.5V8.5zm16 0v7.5l-7 3.5v-7.5l7-3.5z"/>
                        </svg>
                        Claude Code {year}
                    </div>
                </div>
                
                <div class="card-right">
                    <div class="mini-calendar">
                        {mini_calendar_html}
                    </div>
                </div>
            </div>
        </section>
    </div>
</body>
</html>"""

    return html


def main():
    args = sys.argv[1:]

    output_json = "--json" in args
    remote_only = "--remote-only" in args

    remotes = []
    data_paths = []
    merge_sources = {}  # Maps source_name -> target_name
    i = 0
    while i < len(args):
        if args[i] == "--remote" and i + 1 < len(args):
            remotes.append(args[i + 1])
            i += 2
        elif args[i] == "--remote-only" and i + 1 < len(args):
            remotes.append(args[i + 1])
            i += 2
        elif args[i] == "--data-path" and i + 1 < len(args):
            data_paths.append(args[i + 1])
            i += 2
        elif args[i] == "--merge-sources" and i + 1 < len(args):
            # Parse "source=target" mappings (comma-separated)
            for mapping in args[i + 1].split(","):
                if "=" in mapping:
                    src, target = mapping.split("=", 1)
                    merge_sources[src.strip()] = target.strip()
            i += 2
        else:
            i += 1

    print("\n╔══════════════════════════════════════════╗")
    print("║     Claude Code - Year in Review        ║")
    print("╚══════════════════════════════════════════╝\n")

    sources_data = []
    temp_dir = None

    try:
        if remotes:
            temp_dir = Path(tempfile.mkdtemp(prefix="claude-review-"))
            print(f"Fetching data from {len(remotes)} remote(s)...")

            for remote in remotes:
                remote_path = fetch_remote_data(remote, temp_dir)
                if remote_path:
                    data = analyze_claude_dir(remote_path, source_name=remote)
                    if data["timestamps"]:
                        sources_data.append(data)

        for data_path_spec in data_paths:
            source_name = None
            if ":" in data_path_spec:
                last_colon = data_path_spec.rfind(":")
                potential_name = data_path_spec[last_colon + 1 :]
                if "/" not in potential_name and potential_name:
                    path_str = data_path_spec[:last_colon]
                    source_name = potential_name
                else:
                    path_str = data_path_spec
            else:
                path_str = data_path_spec

            path = Path(path_str)
            if path.exists():
                if not source_name:
                    source_name = (
                        path.name if path.name != ".claude" else path.parent.name
                    )
                print(f"  Including data from path: {path_str} (as {source_name})")
                data = analyze_claude_dir(path, source_name=source_name)
                if (
                    data["timestamps"]
                    or data["total_sessions"] > 0
                    or data["model_usage"]
                ):
                    sources_data.append(data)
            else:
                print(f"  Warning: Path not found: {path_str}")

        if not remote_only:
            print("Scanning local Claude Code data...")
            local_dirs = find_claude_data_dirs(include_local=True)

            for claude_dir in local_dirs:
                data = analyze_claude_dir(claude_dir, source_name="local")
                if (
                    data["timestamps"]
                    or data["total_sessions"] > 0
                    or data["model_usage"]
                ):
                    sources_data.append(data)

        if not sources_data:
            print("\nNo Claude Code data found.")
            print("Expected data in ~/.claude/")
            if remotes:
                print("Remote fetch may have failed - check SSH connectivity")
            sys.exit(1)

        print(f"\nAggregating data from {len(sources_data)} source(s)...")
        if merge_sources:
            print(f"  Merging sources: {merge_sources}")
        aggregated = aggregate_data(sources_data, merge_mapping=merge_sources)

        if output_json:

            def serialize(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                if isinstance(obj, set):
                    return list(obj)
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            json_data = {k: v for k, v in aggregated.items() if k != "all_timestamps"}
            print(json.dumps(json_data, default=serialize, indent=2))
        else:
            html = generate_html_report(aggregated)
            output_path = Path.home() / "claude-year-review.html"
            with open(output_path, "w") as f:
                f.write(html)

            print(f"\n✓ Report saved to: {output_path}")
            print(f"✓ Sources: {', '.join(aggregated['sources'])}")
            print(f"✓ Total tokens: {format_number(aggregated['total_tokens'])}")
            print(f"✓ Days active: {aggregated['streaks']['total_days']}")
            print("\nOpening in browser...")
            webbrowser.open(f"file://{output_path}")

    finally:
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
