import hashlib
import sqlite3
import time
from pathlib import Path

from clamp_cc.models import Tag, Turn

_DB_PATH = Path.home() / ".claude" / "clamp_cc_tags.db"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tagging_events (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            turn_index INTEGER,
            turn_content_hash TEXT,
            tag TEXT,
            timestamp INTEGER
        )
    """)
    conn.commit()
    return conn


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def save_tag(session_id: str, turn: Turn) -> None:
    """Persist the current tag for a turn."""
    with _connect() as conn:
        conn.execute(
            """INSERT INTO tagging_events
               (session_id, turn_index, turn_content_hash, tag, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, turn.index, _content_hash(turn.content),
             turn.tag.value, int(time.time())),
        )
        conn.commit()


def load_tags(session_id: str, turns: list[Turn]) -> int:
    """Apply the most recently saved tag for each turn, matched by content hash.

    Returns the number of turns that had a non-NONE tag restored.
    """
    with _connect() as conn:
        rows = conn.execute(
            """SELECT turn_content_hash, tag
               FROM tagging_events
               WHERE session_id = ?
               ORDER BY timestamp ASC""",
            (session_id,),
        ).fetchall()

    # Later rows overwrite earlier ones, last write wins per content hash
    hash_to_tag: dict[str, str] = {ch: tag for ch, tag in rows}

    restored = 0
    for turn in turns:
        saved = hash_to_tag.get(_content_hash(turn.content))
        if saved:
            try:
                turn.tag = Tag(saved)
                if turn.tag != Tag.NONE:
                    restored += 1
            except ValueError:
                pass
    return restored


def trim_old_events(days: int = 90) -> None:
    """Delete tagging events older than `days` days."""
    cutoff = int(time.time()) - days * 86400
    with _connect() as conn:
        conn.execute("DELETE FROM tagging_events WHERE timestamp < ?", (cutoff,))
        conn.commit()
