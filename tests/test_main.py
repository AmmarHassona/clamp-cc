from pathlib import Path

import pytest

from clamp_cc.main import _cwd_project_dir, _encode_project_path


def _make_project_dir(base: Path, name: str) -> Path:
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "session.jsonl").write_text('{"type":"user","isSidechain":false,"message":{"role":"user","content":[]},"uuid":"x","timestamp":"2026-01-01T00:00:00Z"}\n')
    return d


# ---------------------------------------------------------------------------
# Home directory
# ---------------------------------------------------------------------------

def test_home_dir_falls_through_when_longer_projects_exist(tmp_path):
    """Cwd = home dir, which has a project dir, but longer dirs also exist."""
    home = Path("/Users/testuser")
    _make_project_dir(tmp_path, "-Users-testuser")               # home project dir
    _make_project_dir(tmp_path, "-Users-testuser-Github-proj")   # longer project dir

    result = _cwd_project_dir(cwd=home, projects_base=tmp_path)
    assert result is None


def test_home_dir_matches_when_it_is_the_only_project(tmp_path):
    """Cwd = home dir and no longer projects exist — should still match."""
    home = Path("/Users/testuser")
    expected = _make_project_dir(tmp_path, "-Users-testuser")

    result = _cwd_project_dir(cwd=home, projects_base=tmp_path)
    assert result == expected


# ---------------------------------------------------------------------------
# Intermediate parent directory
# ---------------------------------------------------------------------------

def test_parent_dir_falls_through_when_children_exist(tmp_path):
    """Cwd = /Users/testuser/Github — a parent of specific projects."""
    parent = Path("/Users/testuser/Github")
    _make_project_dir(tmp_path, "-Users-testuser-Github")
    _make_project_dir(tmp_path, "-Users-testuser-Github-arabchunk")

    result = _cwd_project_dir(cwd=parent, projects_base=tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# Leaf project (the happy path)
# ---------------------------------------------------------------------------

def test_leaf_project_matches(tmp_path):
    """Cwd = specific project with no children — should match."""
    cwd = Path("/Users/testuser/Github/arabchunk")
    _make_project_dir(tmp_path, "-Users-testuser")
    _make_project_dir(tmp_path, "-Users-testuser-Github")
    expected = _make_project_dir(tmp_path, "-Users-testuser-Github-arabchunk")

    result = _cwd_project_dir(cwd=cwd, projects_base=tmp_path)
    assert result == expected


def test_no_match_when_project_dir_missing(tmp_path):
    """Cwd has no corresponding project directory at all."""
    cwd = Path("/Users/testuser/Github/nonexistent")
    _make_project_dir(tmp_path, "-Users-testuser-Github-arabchunk")

    result = _cwd_project_dir(cwd=cwd, projects_base=tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# Path encoding
# ---------------------------------------------------------------------------

def test_encode_posix_path():
    assert _encode_project_path(Path("/Users/foo/project")) == "-Users-foo-project"


def test_encode_windows_path():
    # Claude Code on Windows replaces both backslashes and colons with dashes
    assert _encode_project_path(Path("C:\\Users\\foo\\project")) == "C--Users-foo-project"


def test_encode_strips_non_ascii():
    # Non-ASCII characters collapse to -, matching Claude Code's encoder
    assert _encode_project_path(Path("/Users/fooé/bar")) == "-Users-foo--bar"
