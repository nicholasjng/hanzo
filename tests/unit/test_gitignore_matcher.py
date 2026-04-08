"""Unit tests for the GitignoreMatcher in hanzo.utils, responsible for writing files to the wheel."""

from hanzo.utils import GitignoreMatcher, GitignorePattern


def make_matcher(*patterns: str) -> GitignoreMatcher:
    """Build a GitignoreMatcher from plain pattern strings.

    Prefix a pattern with ``!`` to make it a negation rule, matching the
    behaviour of ``from_gitignore``.
    """
    parsed: list[GitignorePattern] = []
    for p in patterns:
        negated = p.startswith("!")
        parsed.append(GitignorePattern(p[1:] if negated else p, negated))
    return GitignoreMatcher(parsed)


# ---------------------------------------------------------------------------
# from_gitignore
# ---------------------------------------------------------------------------


def test_from_gitignore_missing_file_returns_empty_matcher(tmp_path):
    matcher = GitignoreMatcher.from_gitignore(tmp_path)
    assert matcher.patterns == []


def test_from_gitignore_skips_blank_lines_and_comments(tmp_path):
    (tmp_path / ".gitignore").write_text("# this is a comment\n\n*.pyc\n")
    matcher = GitignoreMatcher.from_gitignore(tmp_path)
    assert matcher.patterns == [GitignorePattern("*.pyc", False)]


def test_from_gitignore_parses_negation(tmp_path):
    (tmp_path / ".gitignore").write_text("*.log\n!important.log\n")
    matcher = GitignoreMatcher.from_gitignore(tmp_path)
    assert matcher.patterns == [
        GitignorePattern("*.log", False),
        GitignorePattern("important.log", True),
    ]


def test_from_gitignore_star_pattern(tmp_path):
    """Pattern ``*`` (as used in .venv/.gitignore) is parsed as a single pattern."""
    (tmp_path / ".gitignore").write_text("*\n")
    matcher = GitignoreMatcher.from_gitignore(tmp_path)
    assert matcher.patterns == [GitignorePattern("*", False)]


# ---------------------------------------------------------------------------
# ignored(): simple wildcards
# ---------------------------------------------------------------------------


def test_wildcard_matches_by_extension():
    m = make_matcher("*.pyc")
    assert m.ignored("foo.pyc")
    assert not m.ignored("foo.py")


def test_wildcard_matches_at_any_depth():
    m = make_matcher("*.o")
    assert m.ignored("build/foo/bar.o")
    assert not m.ignored("build/foo/bar.obj")


def test_exact_name_pattern():
    m = make_matcher(".DS_Store")
    assert m.ignored(".DS_Store")
    assert m.ignored("subdir/.DS_Store")
    assert not m.ignored("DS_Store")


# ---------------------------------------------------------------------------
# ignored(): negation
# ---------------------------------------------------------------------------


def test_negation_re_includes_file():
    m = make_matcher("*.log", "!important.log")
    assert m.ignored("debug.log")
    assert not m.ignored("important.log")


def test_negation_order_matters_later_wildcard_wins():
    # negation first, then wildcard: file ends up ignored
    m = make_matcher("!important.log", "*.log")
    assert m.ignored("important.log")


# ---------------------------------------------------------------------------
# ignored(): directory-only patterns (trailing slash)
# ---------------------------------------------------------------------------


def test_directory_only_pattern_ignores_directory(tmp_path):
    d = tmp_path / "dist"
    d.mkdir()
    m = make_matcher("dist/")
    assert m.ignored(d)


def test_directory_only_pattern_does_not_ignore_file(tmp_path):
    f = tmp_path / "dist"
    f.write_text("")
    m = make_matcher("dist/")
    assert not m.ignored(f)


# ---------------------------------------------------------------------------
# ignored(): slash patterns (path-rooted matching)
# ---------------------------------------------------------------------------


def test_slash_pattern_matches_at_root():
    m = make_matcher("src/generated")
    assert m.ignored("src/generated")


def test_slash_pattern_matches_relative_subpath():
    m = make_matcher("src/generated")
    assert m.ignored("project/src/generated")


def test_slash_pattern_does_not_match_different_parent():
    m = make_matcher("src/generated")
    assert not m.ignored("lib/generated")
    assert not m.ignored("generated")


# ---------------------------------------------------------------------------
# ignored(): star pattern (e.g. .venv/.gitignore contains only ``*``)
# ---------------------------------------------------------------------------


def test_star_pattern_ignores_any_name():
    m = make_matcher("*")
    assert m.ignored("anything.txt")
    assert m.ignored("deep/nested/file.py")


# ---------------------------------------------------------------------------
# match_files()
# ---------------------------------------------------------------------------


def test_match_files_excludes_ignored_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text("*.pyc\n")
    (tmp_path / "main.py").write_text("")
    (tmp_path / "main.pyc").write_text("")
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "helper.py").write_text("")
    (sub / "helper.pyc").write_text("")

    matcher = GitignoreMatcher.from_gitignore(tmp_path)
    names = {p.name for p in matcher.match_files(tmp_path)}

    assert "main.py" in names
    assert "helper.py" in names
    assert "main.pyc" not in names
    assert "helper.pyc" not in names


def test_match_files_prunes_ignored_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text("build/\n")
    (tmp_path / "main.py").write_text("")
    build = tmp_path / "build"
    build.mkdir()
    (build / "output.o").write_text("")

    matcher = GitignoreMatcher.from_gitignore(tmp_path)
    names = {p.name for p in matcher.match_files(tmp_path)}

    assert "main.py" in names
    assert "output.o" not in names
