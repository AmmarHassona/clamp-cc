from dataclasses import dataclass, field
from enum import Enum


class Tag(Enum):
    NONE = "none"
    PIN = "pin"
    DROP = "drop"
    ARCH = "arch"
    BUG = "bug"
    TASK = "task"
    API = "api"


@dataclass
class Turn:
    index: int
    role: str           # "user" | "assistant"
    content: str        # display text, truncated for TUI
    raw: dict           # full original JSON, never mutated
    token_count: int
    tag: Tag = field(default=Tag.NONE)
