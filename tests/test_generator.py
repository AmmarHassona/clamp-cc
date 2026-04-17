import pytest

from clamp_cc.models import Tag, Turn
from clamp_cc.generator import generate_compact_instruction


def make_turn(index: int, content: str, tag: Tag = Tag.NONE, role: str = "user") -> Turn:
    return Turn(index=index, role=role, content=content, raw={}, token_count=0, tag=tag)


def test_always_starts_with_compact():
    result = generate_compact_instruction([])
    assert result.startswith("/compact")


def test_always_ends_with_summarize_aggressively():
    result = generate_compact_instruction([])
    assert result.endswith("Summarize everything else aggressively.")


def test_no_tagged_turns_minimal_output():
    turns = [make_turn(0, "hello"), make_turn(1, "world")]
    result = generate_compact_instruction(turns)
    assert result == "/compact Summarize everything else aggressively."


def test_pin_tag_in_preserve_section():
    turns = [make_turn(0, "important context", tag=Tag.PIN)]
    result = generate_compact_instruction(turns)
    assert "Always preserve:" in result
    assert "important context" in result


def test_arch_tag_in_focus_section():
    turns = [make_turn(2, "use postgres for storage", tag=Tag.ARCH)]
    result = generate_compact_instruction(turns)
    assert "Focus summary on:" in result
    assert "use postgres for storage" in result


def test_bug_tag_in_focus_section():
    turns = [make_turn(3, "parser crashes on empty input", tag=Tag.BUG)]
    result = generate_compact_instruction(turns)
    assert "Focus summary on:" in result
    assert "parser crashes on empty input" in result


def test_task_tag_in_focus_section():
    turns = [make_turn(4, "implement the TUI next", tag=Tag.TASK)]
    result = generate_compact_instruction(turns)
    assert "Focus summary on:" in result


def test_api_tag_in_focus_section():
    turns = [make_turn(5, "GET /sessions returns list", tag=Tag.API)]
    result = generate_compact_instruction(turns)
    assert "Focus summary on:" in result


def test_drop_tag_in_discard_section():
    turns = [make_turn(1, "irrelevant tangent", tag=Tag.DROP)]
    result = generate_compact_instruction(turns)
    assert "Discard:" in result
    assert "irrelevant tangent" in result


def test_none_tag_not_mentioned():
    turns = [make_turn(0, "ordinary turn", tag=Tag.NONE)]
    result = generate_compact_instruction(turns)
    assert "ordinary turn" not in result
    assert "Always preserve" not in result
    assert "Focus summary on" not in result
    assert "Discard" not in result


def test_multiple_pins():
    turns = [
        make_turn(0, "first important", tag=Tag.PIN),
        make_turn(1, "second important", tag=Tag.PIN),
    ]
    result = generate_compact_instruction(turns)
    assert "first important" in result
    assert "second important" in result


def test_multiple_focus_tags_grouped():
    turns = [
        make_turn(0, "arch decision", tag=Tag.ARCH),
        make_turn(1, "open bug", tag=Tag.BUG),
    ]
    result = generate_compact_instruction(turns)
    assert result.count("Focus summary on:") == 1


def test_section_order():
    turns = [
        make_turn(0, "keep this", tag=Tag.PIN),
        make_turn(1, "arch note", tag=Tag.ARCH),
        make_turn(2, "toss this", tag=Tag.DROP),
    ]
    result = generate_compact_instruction(turns)
    preserve_pos = result.index("Always preserve:")
    focus_pos = result.index("Focus summary on:")
    discard_pos = result.index("Discard:")
    summarize_pos = result.index("Summarize everything")
    assert preserve_pos < focus_pos < discard_pos < summarize_pos


def test_content_truncated_to_100_chars():
    long_content = "x" * 200
    turns = [make_turn(0, long_content, tag=Tag.PIN)]
    result = generate_compact_instruction(turns)
    # identifier snippet should be exactly 100 x's
    assert "x" * 100 in result
    assert "x" * 101 not in result


def test_quotes_in_content_escaped():
    turns = [make_turn(0, 'say "hello"', tag=Tag.PIN)]
    result = generate_compact_instruction(turns)
    # double quotes in content replaced with single quotes to avoid breaking identifier
    assert '"hello"' not in result.split("Always preserve:")[1].split(".")[0]


def test_empty_turns_list():
    result = generate_compact_instruction([])
    assert result == "/compact Summarize everything else aggressively."
