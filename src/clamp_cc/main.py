import argparse
import curses
import sys
from datetime import datetime
from pathlib import Path

from clamp_cc.parser import extract_session_title, parse_session
from clamp_cc.ui import ClampApp


_PROJECTS_BASE = Path.home() / ".claude" / "projects"


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

    project_hash = str(cwd).replace("/", "-")
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


def _latest_jsonl_in(project_dir: Path) -> Path | None:
    candidates = [
        p for p in project_dir.glob("*.jsonl")
        if "subagents" not in p.parts
    ]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


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
        # Best-effort: reverse the hash back to a path for display
        display = project_dir.name.replace("-", "/")
        results.append((display, latest, mtime))
    results.sort(key=lambda x: x[2], reverse=True)
    return results


def _pick_project(projects: list[tuple[str, Path, float]]) -> Path | None:
    """Curses-based arrow-key picker. Returns the selected session path or None."""

    def _run(stdscr: "curses._CursesWindow") -> Path | None:
        curses.curs_set(0)
        selected = 0

        while True:
            stdscr.clear()
            h, w = stdscr.getmaxyx()
            header = "Select a project  (↑/↓ or j/k to navigate, Enter to open, q to quit)"
            stdscr.addstr(0, 0, header[:w - 1])
            stdscr.addstr(1, 0, "─" * (w - 1))

            visible_start = max(0, selected - (h - 4))
            for i, (name, _, mtime) in enumerate(projects):
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
            elif key in (curses.KEY_DOWN, ord("j")) and selected < len(projects) - 1:
                selected += 1
            elif key in (ord("\n"), ord("\r")):
                return projects[selected][1]
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
            session_path = _latest_jsonl_in(project_dir)
            if session_path is None:
                print(f"error: no session files found in {project_dir}", file=sys.stderr)
                sys.exit(1)

        # 3. Interactive picker
        else:
            projects = _all_projects()
            if not projects:
                print("error: no Claude Code sessions found under ~/.claude/projects/", file=sys.stderr)
                sys.exit(1)
            session_path = _pick_project(projects)
            if session_path is None:
                sys.exit(0)

    title = extract_session_title(session_path)
    ClampApp(session_path, title, use_tmux=not args.no_tmux).run()
