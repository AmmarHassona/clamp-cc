# clamp-cc

![CI](https://github.com/AmmarHassona/clamp-cc/actions/workflows/ci.yml/badge.svg)
![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![PyPI](https://img.shields.io/pypi/v/clamp-cc.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

clamp-cc is a terminal UI for taking control of Claude Code's context compaction. Instead of letting `/compact` summarize everything blindly, you open the current session, tag the turns that matter like architectural decisions, open bugs, API contracts, things to drop and hit `g` to generate a targeted `/compact` instruction that tells Claude exactly what to keep, what to focus on, and what to throw away. Tags persist between sessions so you don't have to re-tag every time you open a project.

---

![clamp-cc TUI](media/TUI.svg)

---

## Install

### macOS

```bash
pipx install clamp-cc
```

pipx is the recommended way to install CLI tools on macOS — it creates and manages the virtualenv for you automatically. If you don't have it: `brew install pipx`.

Alternatively, if you prefer managing your own environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install clamp-cc
```

### Windows

Install pipx if you don't have it, then install clamp-cc:

```powershell
pip install pipx
pipx install clamp-cc
```

Or manually with a virtualenv:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install clamp-cc
```

> **Note:** tmux integration is not available on Windows. clamp-cc will always use the clipboard path when running on Windows. If you're using WSL, run clamp-cc inside the WSL terminal where tmux is available.
>
> **Windows Terminal is recommended** over the legacy `cmd.exe` / PowerShell console as the TUI renders correctly there.

## Uninstall

```bash
pipx uninstall clamp-cc
```

Same command on macOS, Linux, and Windows. If you installed into a manual virtualenv, just delete the virtualenv directory.

## Usage

### Session detection

**Auto-detect from current directory** — if you're inside a project that has a Claude Code session, clamp-cc picks it up automatically. If the project has more than one session, a session picker appears so you can choose which one to open:

```bash
cd ~/Github/my-project
clamp
```

![Session picker](media/session-picker.png)

Use `--all-sessions` to always show the picker, even when there's only one session:

```bash
clamp --all-sessions
```

**Project picker** — if you're not in a recognized project directory, clamp-cc shows an interactive list of all your Claude Code projects sorted by most recently modified. Use arrow keys to navigate, Enter to open:

![Project picker](media/project-picker.png)

**Explicit session file** — point directly at a `.jsonl` session file:

```bash
# macOS / Linux
clamp --session ~/.claude/projects/-Users-you-Github-myproject/abc123.jsonl

# Windows (PowerShell)
clamp --session $env:USERPROFILE\.claude\projects\-Users-you-Github-myproject\abc123.jsonl
```

### Workflow

1. Run `clamp` from your project directory
2. Browse turns with arrow keys — the right panel shows the full content of the selected turn
3. Tag turns using the keybindings below
4. Hit `g` to generate the `/compact` instruction — it's copied to clipboard automatically
5. Paste it into Claude Code, or use tmux integration to send it directly (see below)

## When to use clamp-cc

Run it when your session is getting long and you know compaction is coming. The sweet spot is around 60–70% context utilization, before Claude decides what to drop. You can also run it right after an auto-compact to pre-tag what matters for the next round. Tagging early means the next `/compact` preserves the decisions, bugs, and contracts you actually care about instead of summarizing them into oblivion.

## Keybindings

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate turns |
| `p` | Tag as **PIN** — always survive compaction (green) |
| `d` | Tag as **DROP** — explicitly discard (red) |
| `a` | Tag as **ARCH** — architecture decision (yellow) |
| `b` | Tag as **BUG** — open bug (yellow) |
| `t` | Tag as **TASK** — task state (yellow) |
| `c` | Tag as **API** — API contract (yellow) |
| `Space` | Clear tag |
| `g` | Generate `/compact` instruction (auto-copies to clipboard) |
| `?` | Open tag reference / help screen |
| `q` | Quit (asks for confirmation if any turns are tagged) |

The token counter at the bottom updates live as you tag — shows total session tokens, pinned tokens, and tokens being dropped.

## Tagging guide

| Tag | When to use it | Example |
|-----|---------------|---------|
| **PIN** | Decisions that can't be re-derived from the code, things Claude must never lose | "We switched to Postgres because SQLite couldn't handle concurrent writes" |
| **ARCH** | Design choices where the reasoning matters as much as the decision | "Auth is stateless JWT, session state lives in Redis, here's why" |
| **BUG** | Open issues you're mid-fix, enough context to pick back up without re-reading everything | "Parser crashes on empty tool_use blocks, traced to line 47, not fixed yet" |
| **TASK** | Current task state so the next session starts where this one left off | "Finished the modal, next step is wiring the generator to the store" |
| **API** | Contracts, schemas, and interfaces that other parts of the code depend on | "GET /sessions returns `{id, title, mtime}[]`, max 100 results, no pagination yet" |
| **DROP** | Noise, dead ends, and superseded turns that will only confuse the summary | Initial brainstorming that went nowhere, a refactor that got reverted |

## tmux integration

If you're running inside a tmux session, pressing `g` opens a pane picker instead of going straight to the clipboard modal. Select the pane running Claude Code, hit Enter, and clamp-cc fires the `/compact` instruction directly into that pane — no switching windows, no pasting.

https://github.com/user-attachments/assets/d9f74dd6-b2e9-4299-a1b6-e7574ea4a18f

Recommended setup — run Claude Code first, then split and open clamp-cc alongside it:

```bash
# in your existing tmux pane running Claude Code:
tmux split-window -h "cd ~/Github/my-project && clamp"
```

To skip tmux detection and always use the clipboard:

```bash
clamp --no-tmux
```

## How the generated instruction looks

```
/compact Always preserve: ["use postgres, not sqlite — decided after..."],
["auth middleware rewrite is blocked on legal sign-off"].
Focus summary on: ["GET /sessions returns paginated list, max 100..."],
["open bug: parser crashes on empty tool_use blocks"].
Discard: ["initial brainstorm, superseded"], ["tangent about..."].
Summarize everything else aggressively.
```

## Security & privacy

- **No network calls.** clamp-cc is fully offline as it does not contact Anthropic servers or any other host.
- **No telemetry.** Nothing is tracked or logged externally.
- **Local-only file access.** Reads Claude Code session files under `~/.claude/projects/` and writes tags to `~/.claude/clamp_cc_tags.db`. No other paths are touched.
- **No elevated permissions.** Runs as a normal user process. No `sudo`, no `--dangerously-skip-permissions`, no shared system files modified.

## Tag persistence

Tags are saved to `~/.claude/clamp_cc_tags.db` as you work. When you reopen a session, your tags are restored automatically and the session title shows how many were recovered. Events older than 90 days are trimmed on each open.
