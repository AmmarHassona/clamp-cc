import json
from pathlib import Path

from clamp_cc.models import Turn


_SKIP_TYPES = {"queue-operation", "file-history-snapshot", "ai-title"}


def _extract_content(message: dict) -> str:
    """Build display text from a message's content block array."""
    content = message.get("content", [])
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            parts.append(block["text"])
        elif btype == "tool_use":
            parts.append(f"[Tool: {block.get('name', '?')}]")
        elif btype == "thinking":
            snippet = block.get("thinking", "")[:80]
            parts.append(f"[Thinking: {snippet}]")
    return "\n".join(parts)


def _token_count(message: dict) -> int:
    usage = message.get("usage", {})
    return usage.get("output_tokens", 0)


def parse_session(path: Path) -> list[Turn]:
    """Parse a Claude Code JSONL session file into a list of Turn objects."""
    raw_lines: list[dict] = []

    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            raw_lines.append(obj)

    turns: list[tuple[str, dict]] = []  # (timestamp, raw_obj)

    for obj in raw_lines:
        event_type = obj.get("type")
        if event_type in _SKIP_TYPES:
            continue
        if event_type not in ("user", "assistant"):
            continue
        if obj.get("isSidechain", False):
            continue
        timestamp = obj.get("timestamp", "")
        turns.append((timestamp, obj))

    turns.sort(key=lambda x: x[0])

    result: list[Turn] = []
    for index, (_, obj) in enumerate(turns):
        message = obj.get("message", {})
        role = message.get("role", obj.get("type", "unknown"))
        content = _extract_content(message)
        tokens = _token_count(message)
        if not content.strip():
            continue
        result.append(Turn(
            index=index,
            role=role,
            content=content,
            raw=obj,
            token_count=tokens,
        ))

    return result


def extract_session_title(path: Path) -> str:
    """Return the ai-title string for this session, or '' if not found."""
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("type") == "ai-title":
                return obj.get("aiTitle", "")
    return ""


def find_latest_session() -> Path:
    """Find the most recently modified .jsonl session file under ~/.claude/projects/."""
    base = Path.home() / ".claude" / "projects"
    candidates = [
        p for p in base.glob("*/*.jsonl")
        if "subagents" not in p.parts
    ]
    if not candidates:
        raise FileNotFoundError(f"No session files found under {base}")
    return max(candidates, key=lambda p: p.stat().st_mtime)
