from __future__ import annotations

import os
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

import pyperclip
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Footer, Label, ListItem, ListView, LoadingIndicator, Static
from textual.worker import Worker, WorkerState

from clamp_cc import store
from clamp_cc.generator import generate_compact_instruction
from clamp_cc.models import Tag, Turn
from clamp_cc.parser import parse_session

# Tag helpers

_TAG_COLOR: dict[Tag, str] = {
    Tag.NONE: "default",
    Tag.PIN: "green",
    Tag.DROP: "red",
    Tag.ARCH: "yellow",
    Tag.BUG: "yellow",
    Tag.TASK: "yellow",
    Tag.API: "yellow",
}


def _tag_label(tag: Tag) -> str:
    if tag == Tag.NONE:
        return ""
    return f"[{_TAG_COLOR[tag]}]{tag.value.upper()}[/{_TAG_COLOR[tag]}]"

# tmux helpers

def _in_tmux() -> bool:
    return bool(os.environ.get("TMUX"))


def _list_tmux_panes() -> list[tuple[str, str, str]]:
    """Return (pane_id, window_label, current_command) for all panes except this one."""
    current = os.environ.get("TMUX_PANE", "")
    try:
        result = subprocess.run(
            [
                "tmux", "list-panes", "-a",
                "-F", "#{pane_id}\t#{window_index}:#{window_name}\t#{pane_current_command}",
            ],
            capture_output=True, text=True, timeout=5,
        )
        panes = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                pane_id, window, command = parts
                if pane_id != current:
                    panes.append((pane_id, window, command))
        return panes
    except Exception:
        return []


def _send_to_tmux_pane(pane_id: str, text: str) -> None:
    subprocess.run(
        ["tmux", "send-keys", "-t", pane_id, text, "Enter"],
        check=False,
    )

# Compact modal (clipboard path)

class CompactModal(ModalScreen[None]):
    BINDINGS = [
        Binding("ctrl+c", "copy", "Copy again"),
        Binding("escape,q", "dismiss", "Close"),
    ]

    CSS = """
    CompactModal { align: center middle; }
    #modal-container {
        width: 80%; height: 60%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #modal-title { text-align: center; text-style: bold; }
    #modal-copied { text-align: center; margin-bottom: 1; }
    #modal-text {
        height: 1fr; padding: 1;
        border: solid $primary-darken-2;
        background: $surface-darken-1;
    }
    #modal-hint { text-align: center; color: $text-muted; margin-top: 1; }
    """

    def __init__(self, instruction: str) -> None:
        super().__init__()
        self._instruction = instruction
        pyperclip.copy(instruction)

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container"):
            yield Label("Generated /compact Instruction", id="modal-title")
            yield Label("[green]Copied to clipboard[/green]", id="modal-copied")
            yield Static(self._instruction, id="modal-text")
            yield Label("Ctrl+C to copy again  |  Esc to close", id="modal-hint")

    def action_copy(self) -> None:
        pyperclip.copy(self._instruction)
        self.query_one("#modal-hint", Label).update(
            "[green]Copied![/green]  |  Esc to close"
        )

# Help modal

class HelpModal(ModalScreen[None]):
    BINDINGS = [Binding("question_mark,escape", "dismiss", "Close")]

    CSS = """
    HelpModal { align: center middle; }
    #help-container {
        width: 90%; height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #help-title { text-align: center; text-style: bold; margin-bottom: 1; }
    #help-hint  { text-align: center; color: $text-muted; margin-top: 1; }
    """

    _ENTRIES = [
        ("PIN",  "green",  "p", "Must survive compaction verbatim.",
         'Final decisions that can\'t be re-derived ("we\'re using postgres, not sqlite")'),
        ("ARCH", "yellow", "a", "Architectural decision worth summarizing carefully.",
         'Design choices with reasoning ("chose event sourcing for audit trail")'),
        ("BUG",  "yellow", "b", "Open bug Claude needs to stay aware of.",
         'Known issues mid-fix ("parser crashes on empty tool_use blocks")'),
        ("TASK", "yellow", "t", "Current task state.",
         'Where you are mid-task ("completed steps 1-3, currently on step 4")'),
        ("API",  "yellow", "c", "API contract or interface definition.",
         "Endpoints, function signatures, schemas that other code depends on"),
        ("DROP", "red",    "d", "Explicitly discard this turn.",
         "Tool call noise, superseded decisions, tangents"),
    ]

    def compose(self) -> ComposeResult:
        rows = "\n".join(
            f" [{color}]{tag:<4}[/{color}]  [{color}]{key}[/{color}]   {desc}\n"
            f"        [dim]Use for: {example}[/dim]"
            for tag, color, key, desc, example in self._ENTRIES
        )
        with Vertical(id="help-container"):
            yield Label("Tag reference", id="help-title")
            yield Static(rows, id="help-body")
            yield Label("? or Esc to close", id="help-hint")


# tmux pane picker modal

class TmuxPickerModal(ModalScreen[bool]):
    """Select a tmux pane to send the /compact instruction to."""

    BINDINGS = [
        Binding("escape", "cancel", "Clipboard only"),
    ]

    CSS = """
    TmuxPickerModal { align: center middle; }
    #tmux-container {
        width: 80%; height: 70%;
        border: thick $success;
        background: $surface;
        padding: 1 2;
    }
    #tmux-title { text-align: center; text-style: bold; }
    #tmux-copied { text-align: center; }
    #tmux-preview { color: $text-muted; margin-bottom: 1; }
    #tmux-pane-list { height: 1fr; border: solid $primary-darken-2; }
    #tmux-hint { text-align: center; color: $text-muted; margin-top: 1; }
    """

    def __init__(self, instruction: str, panes: list[tuple[str, str, str]]) -> None:
        super().__init__()
        self._instruction = instruction
        self._panes = panes
        pyperclip.copy(instruction)

    def compose(self) -> ComposeResult:
        snippet = self._instruction[:70] + ("…" if len(self._instruction) > 70 else "")
        with Vertical(id="tmux-container"):
            yield Label("Send to tmux pane", id="tmux-title")
            yield Label("[green]Also copied to clipboard[/green]", id="tmux-copied")
            yield Label(f'[dim]{snippet}[/dim]', id="tmux-preview")
            yield ListView(
                *[
                    ListItem(Label(f"[cyan]{pane_id}[/cyan]  {window}  [dim][{command}][/dim]"))
                    for pane_id, window, command in self._panes
                ],
                id="tmux-pane-list",
            )
            yield Label("Enter=send  |  Esc=clipboard only", id="tmux-hint")

    def on_mount(self) -> None:
        self.query_one("#tmux-pane-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        pane_id = self._panes[idx][0]
        _send_to_tmux_pane(pane_id, self._instruction)
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

# Quit confirmation modal

class QuitModal(ModalScreen[bool]):
    BINDINGS = [
        Binding("y", "confirm", "Yes, quit"),
        Binding("n,escape", "cancel", "No, go back"),
    ]

    CSS = """
    QuitModal { align: center middle; }
    #quit-box {
        width: auto; height: auto;
        padding: 2 4;
        border: thick $warning;
        background: $surface;
    }
    #quit-msg { margin-bottom: 1; }
    #quit-hint { color: $text-muted; }
    """

    def __init__(self, n_tagged: int) -> None:
        super().__init__()
        self._n_tagged = n_tagged

    def compose(self) -> ComposeResult:
        s = "s" if self._n_tagged != 1 else ""
        with Vertical(id="quit-box"):
            yield Label(
                f"You have {self._n_tagged} tagged turn{s}. Quit without generating?",
                id="quit-msg",
            )
            yield Label("y = quit  |  n / Esc = go back", id="quit-hint")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

# Turn row widget

class TurnRow(ListItem):
    def __init__(self, turn: Turn) -> None:
        super().__init__()
        self.turn = turn

    def compose(self) -> ComposeResult:
        yield Label(self._line())

    def _line(self) -> str:
        tag_str = _tag_label(self.turn.tag)
        snippet = self.turn.content[:80].replace("\n", " ")
        role_color = "cyan" if self.turn.role == "user" else "magenta"
        role_str = f"[{role_color}]{self.turn.role[:4].upper()}[/{role_color}]"
        return (
            f"[dim]{self.turn.index:>3}[/dim] "
            f"{role_str} "
            f"[dim]{self.turn.token_count:>5}tok[/dim]  "
            f"{tag_str:<18}  "
            f"{snippet}"
        )

    def refresh_label(self) -> None:
        self.query_one(Label).update(self._line())

# Main body (mounted after loading)

class _MainBody(Widget):
    DEFAULT_CSS = "_MainBody { height: 1fr; }"

    def __init__(self, turns: list[Turn], title: str) -> None:
        super().__init__()
        self._turns = turns
        self._title = title

    def compose(self) -> ComposeResult:
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield Label(self._title or "Untitled session", id="session-title")
                yield ListView(*[TurnRow(t) for t in self._turns], id="turn-list")
            with Vertical(id="right"):
                yield ScrollableContainer(
                    Static("", id="detail"),
                    id="right-scroll",
                )

# Main app

class ClampApp(App[None]):
    CSS = """
    #session-title {
        text-style: bold; padding: 0 1;
        background: $primary-darken-2; color: $text;
    }
    #left { width: 50%; border-right: solid $primary-darken-2; }
    #turn-list { height: 1fr; }
    #right { width: 1fr; }
    #detail { height: 1fr; padding: 0 1; }
    #token-bar {
        height: 1; padding: 0 1;
        background: $surface-darken-1; color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("p", "tag('pin')", "PIN"),
        Binding("d", "tag('drop')", "DROP"),
        Binding("a", "tag('arch')", "ARCH"),
        Binding("b", "tag('bug')", "BUG"),
        Binding("t", "tag('task')", "TASK"),
        Binding("c", "tag('api')", "API"),
        Binding("space", "tag('none')", "CLEAR"),
        Binding("g", "generate", "GENERATE"),
        Binding("question_mark", "help", "HELP"),
        Binding("q", "quit", "QUIT"),
    ]

    def __init__(self, session_path: Path, title: str, use_tmux: bool = True) -> None:
        super().__init__()
        self._session_path = session_path
        self._title = title
        self._use_tmux = use_tmux
        self._turns: list[Turn] = []
        self._has_generated = False

    def compose(self) -> ComposeResult:
        yield LoadingIndicator()
        yield Footer()

    def on_mount(self) -> None:
        self._load_session()

    @work(thread=True, name="load_session")
    def _load_session(self) -> tuple[list[Turn], int]:
        turns = parse_session(self._session_path)
        n_restored = 0
        try:
            n_restored = store.load_tags(self._session_path.stem, turns)
            store.trim_old_events()
        except Exception:
            print("clamp-cc: failed to load persisted tags:", file=sys.stderr)
            traceback.print_exc()
        return turns, n_restored

    async def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.name != "load_session" or event.state != WorkerState.SUCCESS:
            return

        self._turns, n_restored = event.worker.result
        await self.query_one(LoadingIndicator).remove()

        footer = self.query_one(Footer)
        await self.mount(Static(self._token_bar_text(), id="token-bar"), before=footer)
        await self.mount(_MainBody(self._turns, self._title), before=self.query_one("#token-bar"))

        if n_restored > 0:
            s = "s" if n_restored != 1 else ""
            base = self._title or "Untitled session"
            self.query_one("#session-title", Label).update(
                f"{base}  [dim]({n_restored} tag{s} restored)[/dim]"
            )

        self.query_one("#turn-list", ListView).focus()
        if self._turns:
            self._update_detail(self._turns[0])

    # Token bar

    def _token_bar_text(self) -> str:
        total = sum(t.token_count for t in self._turns)
        pinned = sum(t.token_count for t in self._turns if t.tag == Tag.PIN)
        dropping = sum(t.token_count for t in self._turns if t.tag == Tag.DROP)
        return (
            f"Total: {total:,} tok  |  "
            f"[green]Pinned: {pinned:,}[/green]  |  "
            f"[red]Dropping: {dropping:,}[/red]"
        )

    def _update_token_bar(self) -> None:
        self.query_one("#token-bar", Static).update(self._token_bar_text())

    # Detail panel

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None or not isinstance(event.item, TurnRow):
            return
        self._update_detail(event.item.turn)

    def _update_detail(self, turn: Turn) -> None:
        ts_raw = turn.raw.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            ts_str = dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError):
            ts_str = ts_raw
        header = f"[dim]Turn {turn.index} · {turn.role} · {ts_str}[/dim]\n\n"
        self.query_one("#detail", Static).update(header + turn.content)

    # Tagging

    def _selected_row(self) -> TurnRow | None:
        lv = self.query_one("#turn-list", ListView)
        item = lv.highlighted_child
        return item if isinstance(item, TurnRow) else None

    def _apply_tag(self, tag: Tag) -> None:
        row = self._selected_row()
        if row is None:
            return
        row.turn.tag = tag
        row.refresh_label()
        self._update_token_bar()
        try:
            store.save_tag(self._session_path.stem, row.turn)
        except Exception:
            print("clamp-cc: failed to persist tag:", file=sys.stderr)
            traceback.print_exc()

    def action_tag(self, tag_name: str) -> None:
        self._apply_tag(Tag(tag_name))

    # Generate

    def action_help(self) -> None:
        self.push_screen(HelpModal())

    def action_generate(self) -> None:
        instruction = generate_compact_instruction(self._turns)
        self._has_generated = True

        if self._use_tmux and _in_tmux():
            panes = _list_tmux_panes()
            if panes:
                def _on_tmux_done(sent: bool) -> None:
                    if not sent:
                        self.push_screen(CompactModal(instruction))

                self.push_screen(TmuxPickerModal(instruction, panes), callback=_on_tmux_done)
                return

        self.push_screen(CompactModal(instruction))

    # Quit

    def action_quit(self) -> None:
        n_tagged = sum(1 for t in self._turns if t.tag != Tag.NONE)
        if n_tagged == 0 or self._has_generated:
            self.exit()
        else:
            self.push_screen(
                QuitModal(n_tagged),
                callback=lambda confirmed: self.exit() if confirmed else None,
            )
