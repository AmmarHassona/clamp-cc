from clamp_cc.models import Tag, Turn


def _identifier(turn: Turn) -> str:
    snippet = turn.content[:100].replace("\n", " ").replace('"', "'")
    return f'turn {turn.index}: "{snippet}"'


def generate_compact_instruction(turns: list[Turn]) -> str:
    preserve = [t for t in turns if t.tag == Tag.PIN]
    focus = [t for t in turns if t.tag in (Tag.ARCH, Tag.BUG, Tag.TASK, Tag.API)]
    discard = [t for t in turns if t.tag == Tag.DROP]

    parts: list[str] = ["/compact"]

    if preserve:
        items = ", ".join(f"[{_identifier(t)}]" for t in preserve)
        parts.append(f"Always preserve: {items}.")

    if focus:
        items = ", ".join(f"[{_identifier(t)}]" for t in focus)
        parts.append(f"Focus summary on: {items}.")

    if discard:
        items = ", ".join(f"[{_identifier(t)}]" for t in discard)
        parts.append(f"Discard: {items}.")

    parts.append("Summarize everything else aggressively.")

    return " ".join(parts)
