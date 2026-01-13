# AI Tools Year in Review

A Python script that analyzes your AI coding assistant usage data and generates a beautiful HTML report with visualizations and a shareable Twitter card.

## Supported Tools

- **Claude Code** (`~/.claude/`)
- **Continue.dev** (`~/.continue/`)
- **OpenAI Codex CLI** (`~/.codex/`)
- **OpenCode** (`~/.local/share/opencode/`)

## Features

- **Multi-tool support**: Aggregates data from Claude Code, Continue.dev, Codex, and OpenCode
- **This Week view**: 7-day sparkline with daily token counts and trend visualization
- **All Time stats**: Total tokens, total days, and longest streak across all tools
- **Year Activity calendar**: Full-year heatmap showing daily usage
- **Per-tool breakdown**: Individual stats cards for each AI tool with brand colors
- **Remote host support**: Fetch data from remote machines via SSH/rsync
- **Twitter-ready share card**: One-click sharing with auto-generated PNG

## Requirements

- Python 3 (no external dependencies)
- `rsync` (for remote data fetching)
- SSH access configured for remote hosts

## Usage

### Basic Usage

```bash
# Analyze all local AI tools
python3 claude-year-review.py

# Include data from a remote host (fetches all tools)
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

## CLI Options

| Option | Description |
|--------|-------------|
| `--remote user@host` | Include remote SSH host - fetches all AI tools (can be specified multiple times) |
| `--remote-only user@host` | Analyze remote host only, skip local data |
| `--data-path /path/.claude` | Include pre-fetched data from a path. Supports `path:name` format |
| `--merge-sources "source=target"` | Merge source data into target (comma-separated for multiple) |
| `--json` | Output statistics as JSON instead of generating HTML report |

## Output

The script generates `~/ai-year-review.html` and opens it in your browser.

### Report Sections

1. **Tool Cards**: Per-tool breakdown showing tokens, days, and messages for each AI tool
2. **This Week**: Today's token count + 7-day trend sparkline with data points
3. **All Time**: Total tokens, total days active, longest streak
4. **Year Activity**: Full calendar heatmap for the current year
5. **Share Card**: Twitter-ready card with all-time stats and mini calendar

### Tool Colors

| Tool | Color |
|------|-------|
| Claude Code | Orange (#ff6b35) |
| Continue.dev | Teal (#4ecdc4) |
| Codex | Green (#22c55e) |
| OpenCode | Purple (#a855f7) |

## Remote Data Fetching

When using `--remote`, the script fetches data for ALL supported tools:

```bash
python3 claude-year-review.py --remote user@workstation
```

This will rsync:
- `~/.claude/` (Claude Code)
- `~/.continue/` (Continue.dev)
- `~/.codex/` (Codex)
- `~/.local/share/opencode/` (OpenCode)

Remote data appears as a separate source in the legend, allowing you to compare usage across machines.

## Sharing on Twitter/X

Click **"Share on X"** to:
1. Open Twitter with pre-filled text including your token count
2. Automatically download a PNG image of your stats card
3. Attach the downloaded image to complete your tweet

## Screenshots

The report includes:
- Dark theme optimized for sharing
- Gradient accents and smooth animations
- Responsive design for all screen sizes
- Tool-specific brand colors in visualizations

## License

MIT
