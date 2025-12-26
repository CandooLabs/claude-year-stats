# Claude Code Year in Review

A Python script that analyzes your Claude Code usage data and generates an interactive HTML report with visualizations.

## Features

- Analyzes Claude Code usage data from `~/.claude` directory
- Supports multiple data sources: local, remote hosts (via SSH/rsync), and pre-fetched paths
- Generates an HTML report with:
  - Token usage statistics (total and weekly breakdown)
  - Activity calendar with daily usage visualization
  - Usage streaks (current and longest)
  - Model usage breakdown (top 5 models)
  - Per-source statistics when using multiple data sources
- Merge data from multiple sources into unified statistics
- JSON output option for programmatic access

## Requirements

- Python 3 (no external dependencies)
- `rsync` (for remote data fetching)
- SSH access configured for remote hosts

## Usage

### Basic Usage

```bash
# Analyze local Claude Code data only
python3 claude-year-review.py

# Include data from a remote host
python3 claude-year-review.py --remote user@hostname

# Include multiple remote hosts
python3 claude-year-review.py --remote user@host1 --remote user@host2

# Analyze remote host only (skip local data)
python3 claude-year-review.py --remote-only user@hostname
```

### Including Pre-fetched Data

```bash
# Include data from a specific path
python3 claude-year-review.py --data-path /path/to/.claude

# Include data with a custom source name (path:name format)
python3 claude-year-review.py --data-path /backups/old-machine/.claude:old-laptop
```

### Merging Sources

```bash
# Merge one source into another (e.g., backup data into current host)
python3 claude-year-review.py --data-path /backup/.claude:backup --merge-sources "backup=local"

# Merge multiple sources (comma-separated)
python3 claude-year-review.py --merge-sources "source1=target,source2=target"
```

### JSON Output

```bash
# Output aggregated statistics as JSON instead of HTML
python3 claude-year-review.py --json
```

### Combined Examples

```bash
# Full example: local + remote + backup data, merged
python3 claude-year-review.py \
  --remote user@workstation \
  --data-path /backups/.claude:old-backup \
  --merge-sources "old-backup=local"

# Multiple remotes with JSON output
python3 claude-year-review.py --remote host1 --remote host2 --json
```

## CLI Options

| Option | Description |
|--------|-------------|
| `--remote user@host` | Include remote SSH host (can be specified multiple times) |
| `--remote-only user@host` | Analyze remote host only, skip local data |
| `--data-path /path/.claude` | Include pre-fetched data from a path. Supports `path:name` format to set custom source name |
| `--merge-sources "source=target"` | Merge source data into target (comma-separated for multiple) |
| `--json` | Output statistics as JSON instead of generating HTML report |

## Output

By default, the script generates `~/claude-year-review.html` and opens it in your browser. The report includes:

- **Token Usage**: Total tokens consumed with weekly breakdown grid
- **Activity Calendar**: Visual representation of daily usage across the year
- **Usage Streaks**: Current streak and longest streak statistics
- **Model Usage**: Top 5 Claude models used
- **Per-Source Stats**: When using multiple sources, shows tokens, days, sessions, and events per source

With `--json`, outputs aggregated statistics to stdout for programmatic use.
