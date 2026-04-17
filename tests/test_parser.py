from pathlib import Path

import pytest

from clamp_cc.models import Tag, Turn
from clamp_cc.parser import parse_session

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def test_returns_list_of_turns():
    turns = parse_session(FIXTURE)
    assert isinstance(turns, list)
    assert all(isinstance(t, Turn) for t in turns)


def test_skips_noise_events():
    turns = parse_session(FIXTURE)
    # Fixture has: 1 user turn, 2 assistant turns (sidechain filtered)
    assert len(turns) == 3


def test_sidechain_filtered():
    turns = parse_session(FIXTURE)
    for t in turns:
        assert not t.raw.get("isSidechain", False)


def test_roles():
    turns = parse_session(FIXTURE)
    roles = [t.role for t in turns]
    assert roles[0] == "user"
    assert roles[1] == "assistant"
    assert roles[2] == "assistant"


def test_index_sequential():
    turns = parse_session(FIXTURE)
    assert [t.index for t in turns] == list(range(len(turns)))


def test_user_turn_content_joins_text_blocks():
    turns = parse_session(FIXTURE)
    user_turn = turns[0]
    assert "Read the README" in user_turn.content
    assert "pyproject.toml" in user_turn.content


def test_assistant_tool_use_rendered():
    turns = parse_session(FIXTURE)
    # Second turn (index 1) has thinking + tool_use blocks
    asst_turn = turns[1]
    assert "[Tool: Read]" in asst_turn.content


def test_assistant_thinking_rendered():
    turns = parse_session(FIXTURE)
    asst_turn = turns[1]
    assert "[Thinking:" in asst_turn.content


def test_token_count_assistant():
    turns = parse_session(FIXTURE)
    # turns[1]: input=500 + output=120 = 620
    # turns[2]: input=800 + output=45 = 845
    assert turns[1].token_count == 620
    assert turns[2].token_count == 845


def test_default_tag_is_none():
    turns = parse_session(FIXTURE)
    for t in turns:
        assert t.tag == Tag.NONE


def test_empty_content_turns_excluded():
    from pathlib import Path
    import tempfile, json

    empty_turn = {
        "type": "user",
        "isSidechain": False,
        "message": {"role": "user", "content": [{"type": "text", "text": "   "}]},
        "uuid": "uuid-empty",
        "timestamp": "2026-04-16T09:00:00.000Z",
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(empty_turn) + "\n")
        tmp = Path(f.name)

    turns = parse_session(tmp)
    tmp.unlink()
    assert len(turns) == 0


def test_sorted_by_timestamp():
    turns = parse_session(FIXTURE)
    timestamps = [t.raw.get("timestamp", "") for t in turns]
    assert timestamps == sorted(timestamps)
