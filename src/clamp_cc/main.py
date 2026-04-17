import argparse
import curses
import sys
from datetime import datetime
from pathlib import Path

from clamp_cc.parser import extract_session_title
from clamp_cc.ui import ClampApp


_PROJECTS_BASE = Path.home() / ".claude" / "projects"


def _encode_project_path(path: Path) -> str:
    """Encode an absolute path into Claude Code's project directory name.

    Replaces path separators (both / and \\) and drive-letter colons with -,
    then maps any remaining non-ASCII-alphanumeric character to - as well.
    Matches the algorithm Claude Code uses on macOS, Linux, and Windows.
    """
    raw = str(path).replace("\\", "-").replace("/", "-")
    return "".join(
        c if (c.isascii() and c.isalnum()) or c == "-" else "-"
        for c in raw
    )


def _cwd_project_dir(
    cwd: Path | None = None,
    projects_base: Path | None = None,
) -> Path | None:
    """Return the ~/.claude/projects/<hash> dir for cwd if it's an unambiguous leaf project.

    Returns None if the directory doesn't exist OR if its hash is a prefix of
    another project directory (e.g. /Users/foo matching -Users-foo when
    -Users-foo-Github-project also exists).
    """
    if cwd is None:
        cwd = Path.cwd()
    if projects_base is None:
        projects_base = _PROJECTS_BASE

    project_hash = _encode_project_path(cwd)
    project_dir = projects_base / project_hash

    if not project_dir.is_dir():
        return None

    # Reject if this hash is a prefix of any longer project directory
    # It means cwd is a parent directory, not an actual project root.
    prefix = project_hash + "-"
    for sibling in projects_base.iterdir():
        if sibling.is_dir() and sibling.name.startswith(prefix):
            return None

    return project_dir


def _jsonl_files_in(project_dir: Path) -> list[Path]:
    return [
        p for p in project_dir.glob("*.jsonl")
        if "subagents" not in p.parts
    ]


def _latest_jsonl_in(project_dir: Path) -> Path | None:
    candidates = _jsonl_files_in(project_dir)
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _all_sessions_in(project_dir: Path) -> list[tuple[str, Path, float]]:
    """Return (display_label, path, mtime) for every session in a project, newest first."""
    results = []
    for p in _jsonl_files_in(project_dir):
        mtime = p.stat().st_mtime
        title = extract_session_title(p, max_lines=500) or p.stem
        results.append((title, p, mtime))
    results.sort(key=lambda x: x[2], reverse=True)
    return results


def _all_projects() -> list[tuple[str, Path, float]]:
    """Return (display_name, latest_jsonl, mtime) for every project, newest first."""
    results = []
    if not _PROJECTS_BASE.exists():
        return results
    for project_dir in _PROJECTS_BASE.iterdir():
        if not project_dir.is_dir():
            continue
        latest = _latest_jsonl_in(project_dir)
        if latest is None:
            continue
        mtime = latest.stat().st_mtime
        display = project_dir.name.replace("-", "/")
        results.append((display, latest, mtime))
    results.sort(key=lambda x: x[2], reverse=True)
    return results


def _curses_picker(header: str, items: list[tuple[str, Path, float]]) -> Path | None:
    """Generic curses arrow-key picker. Returns the selected path or None."""

    def _run(stdscr: "curses._CursesWindow") -> Path | None:
        curses.curs_set(0)
        selected = 0

        while True:
            stdscr.clear()
            h, w = stdscr.getmaxyx()
            stdscr.addstr(0, 0, header[:w - 1])
            stdscr.addstr(1, 0, "─" * (w - 1))

            visible_start = max(0, selected - (h - 4))
            for i, (name, _, mtime) in enumerate(items):
                row = i - visible_start
                y = row + 2
                if y < 2 or y >= h - 1:
                    continue
                dt = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                line = f"  {dt}  {name}"
                if i == selected:
                    stdscr.attron(curses.A_REVERSE)
                    stdscr.addstr(y, 0, line[:w - 1])
                    stdscr.attroff(curses.A_REVERSE)
                else:
                    stdscr.addstr(y, 0, line[:w - 1])

            stdscr.refresh()
            key = stdscr.getch()

            if key in (curses.KEY_UP, ord("k")) and selected > 0:
                selected -= 1
            elif key in (curses.KEY_DOWN, ord("j")) and selected < len(items) - 1:
                selected += 1
            elif key in (ord("\n"), ord("\r")):
                return items[selected][1]
            elif key == ord("q"):
                return None

    return curses.wrapper(_run)


def main() -> None:
    arg_parser = argparse.ArgumentParser(
        prog="clamp",
        description="Interactive Claude Code context compaction tool.",
    )
    arg_parser.add_argument(
        "--session",
        metavar="PATH",
        type=Path,
        default=None,
        help="Path to a specific .jsonl session file (default: auto-detect).",
    )
    arg_parser.add_argument(
        "--no-tmux",
        action="store_true",
        default=False,
        help="Skip tmux pane picker and always use clipboard.",
    )
    arg_parser.add_argument(
        "--all-sessions",
        action="store_true",
        default=False,
        help="Always show the session picker, even if the project has only one session.",
    )
    args = arg_parser.parse_args()

    # 1. Explicit path
    if args.session:
        session_path = args.session
        if not session_path.exists():
            print(f"error: session file not found: {session_path}", file=sys.stderr)
            sys.exit(1)

    # 2. Auto-detect from cwd
    else:
        project_dir = _cwd_project_dir()
        if project_dir is not None:
            sessions = _all_sessions_in(project_dir)
            if not sessions:
                print(f"error: no session files found in {project_dir}", file=sys.stderr)
                sys.exit(1)
            if len(sessions) == 1 and not args.all_sessions:
                session_path = sessions[0][1]
            else:
                session_path = _curses_picker(
                    "Select a session  (↑/↓ or j/k to navigate, Enter to open, q to quit)",
                    sessions,
                )
                if session_path is None:
                    sys.exit(0)

        # 3. Project picker
        else:
            projects = _all_projects()
            if not projects:
                print("error: no Claude Code sessions found under ~/.claude/projects/", file=sys.stderr)
                sys.exit(1)
            session_path = _curses_picker(
                "Select a project  (↑/↓ or j/k to navigate, Enter to open, q to quit)",
                projects,
            )
            if session_path is None:
                sys.exit(0)

    title = extract_session_title(session_path)
    ClampApp(session_path, title, use_tmux=not args.no_tmux).run()
