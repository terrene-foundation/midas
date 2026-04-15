"""Tier 1 tests for release module (changelog + version management).

Covers:
- ChangelogEntry formatting (scope, breaking, plain)
- ChangelogGenerator section grouping and markdown output
- ChangelogGenerator _parse_commits via mocked subprocess
- Commit pattern matching for conventional commits
- get_version() from pyproject.toml and fallback
- validate_version_consistency() for matching/mismatching/missing files
- Edge cases: pre-release versions, malformed commits, empty git output
"""

import os
import re
import subprocess
import textwrap
import tomllib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from midas.release.changelog import (
    ChangelogEntry,
    ChangelogGenerator,
    _COMMIT_PATTERN,
)
from midas.release.version import (
    get_version,
    validate_version_consistency,
)


# ---------------------------------------------------------------------------
# ChangelogEntry formatting
# ---------------------------------------------------------------------------


class TestChangelogEntryFormat:
    """Tests for ChangelogEntry.format() output."""

    def test_format_plain_entry(self):
        """Plain entry without scope or breaking flag formats correctly."""
        entry = ChangelogEntry(
            commit_hash="abcdef1234567890",
            commit_type="feat",
            scope="",
            description="add new feature",
            breaking=False,
        )
        result = entry.format()
        assert result == "- add new feature (abcdef1)"

    def test_format_entry_with_scope(self):
        """Entry with scope includes bold scope prefix."""
        entry = ChangelogEntry(
            commit_hash="abcdef1234567890",
            commit_type="fix",
            scope="api",
            description="resolve rate limiting issue",
            breaking=False,
        )
        result = entry.format()
        assert result == "- **api**: resolve rate limiting issue (abcdef1)"

    def test_format_entry_with_breaking_flag(self):
        """Breaking entry includes BREAKING prefix."""
        entry = ChangelogEntry(
            commit_hash="abcdef1234567890",
            commit_type="feat",
            scope="auth",
            description="replace OAuth provider",
            breaking=True,
        )
        result = entry.format()
        assert result == "- **BREAKING** **auth**: replace OAuth provider (abcdef1)"

    def test_format_breaking_without_scope(self):
        """Breaking entry without scope shows BREAKING but no scope."""
        entry = ChangelogEntry(
            commit_hash="1234567890abcde",
            commit_type="refactor",
            scope="",
            description="restructure public API",
            breaking=True,
        )
        result = entry.format()
        assert result == "- **BREAKING** restructure public API (1234567)"

    def test_format_commit_hash_truncated_to_seven(self):
        """Commit hash is truncated to first 7 characters."""
        entry = ChangelogEntry(
            commit_hash="a1b2c3d4e5f6g7h8",
            commit_type="chore",
            scope="",
            description="update deps",
            breaking=False,
        )
        result = entry.format()
        assert "(a1b2c3d)" in result

    def test_format_short_commit_hash(self):
        """Short commit hash (fewer than 7 chars) is handled gracefully."""
        entry = ChangelogEntry(
            commit_hash="abc",
            commit_type="fix",
            scope="",
            description="tiny fix",
            breaking=False,
        )
        result = entry.format()
        assert "(abc)" in result


# ---------------------------------------------------------------------------
# Conventional commit pattern matching
# ---------------------------------------------------------------------------


class TestCommitPattern:
    """Tests for the conventional commit regex _COMMIT_PATTERN."""

    def test_pattern_matches_feat(self):
        match = _COMMIT_PATTERN.match("feat: add new feature")
        assert match is not None
        assert match.group("type") == "feat"
        assert match.group("scope") is None
        assert match.group("description") == "add new feature"

    def test_pattern_matches_fix_with_scope(self):
        match = _COMMIT_PATTERN.match("fix(api): resolve timeout")
        assert match is not None
        assert match.group("type") == "fix"
        assert match.group("scope") == "api"
        assert match.group("description") == "resolve timeout"

    def test_pattern_matches_docs(self):
        match = _COMMIT_PATTERN.match("docs: update readme")
        assert match is not None
        assert match.group("type") == "docs"

    def test_pattern_matches_style(self):
        match = _COMMIT_PATTERN.match("style: fix formatting")
        assert match is not None
        assert match.group("type") == "style"

    def test_pattern_matches_refactor(self):
        match = _COMMIT_PATTERN.match("refactor(core): simplify loop")
        assert match is not None
        assert match.group("type") == "refactor"

    def test_pattern_matches_test(self):
        match = _COMMIT_PATTERN.match("test: add unit tests")
        assert match is not None
        assert match.group("type") == "test"

    def test_pattern_matches_chore(self):
        match = _COMMIT_PATTERN.match("chore(ci): update pipeline")
        assert match is not None
        assert match.group("type") == "chore"

    def test_pattern_rejects_non_conventional(self):
        match = _COMMIT_PATTERN.match("random commit message")
        assert match is None

    def test_pattern_rejects_unknown_type(self):
        match = _COMMIT_PATTERN.match("build: compile project")
        assert match is None

    def test_pattern_matches_space_only_description(self):
        """Trailing space after colon matches (description captures the space).

        The regex uses `.+` which accepts any character including whitespace.
        A message like "feat: " is therefore treated as valid with description " ".
        """
        match = _COMMIT_PATTERN.match("feat: ")
        assert match is not None
        assert match.group("description") == " "

    def test_pattern_rejects_colon_only_no_description(self):
        """Type with colon but nothing after it does not match."""
        match = _COMMIT_PATTERN.match("feat:")
        assert match is None

    def test_pattern_rejects_exclamation_breaking_syntax(self):
        """The regex does NOT support conventional commits v2 '!' breaking syntax.

        'feat!: ...' is not recognized -- the '!' between type and colon
        prevents the match. Breaking changes are detected via "BREAKING" in
        the message text, not via the '!' suffix.
        """
        match = _COMMIT_PATTERN.match("feat!: BREAKING change to API")
        assert match is None

    def test_pattern_matches_breaking_keyword_in_description(self):
        """BREAKING keyword in description text is matched normally."""
        match = _COMMIT_PATTERN.match("feat: BREAKING change to API")
        assert match is not None
        assert match.group("type") == "feat"
        assert "BREAKING" in match.group("description")

    def test_pattern_matches_multi_word_scope(self):
        match = _COMMIT_PATTERN.match("feat(data-flow): new transform")
        assert match is not None
        assert match.group("scope") == "data-flow"

    def test_pattern_matches_all_recognized_types(self):
        """Every type in the regex character class is recognized."""
        for t in ["feat", "fix", "docs", "style", "refactor", "test", "chore"]:
            match = _COMMIT_PATTERN.match(f"{t}: some description")
            assert match is not None, f"type '{t}' should be recognized"


# ---------------------------------------------------------------------------
# ChangelogGenerator section grouping
# ---------------------------------------------------------------------------


class TestChangelogGeneratorSections:
    """Tests for ChangelogGenerator.generate() section grouping logic."""

    @patch.object(ChangelogGenerator, "_parse_commits")
    def test_generate_groups_feat_into_features(self, mock_parse):
        mock_parse.return_value = [
            ChangelogEntry(
                commit_hash="aaa1111",
                commit_type="feat",
                scope="",
                description="new thing",
                breaking=False,
            )
        ]
        gen = ChangelogGenerator()
        output = gen.generate()

        assert "### Features" in output
        assert "new thing" in output
        assert "### Bug Fixes" not in output

    @patch.object(ChangelogGenerator, "_parse_commits")
    def test_generate_groups_fix_into_bug_fixes(self, mock_parse):
        mock_parse.return_value = [
            ChangelogEntry(
                commit_hash="bbb2222",
                commit_type="fix",
                scope="core",
                description="fix crash",
                breaking=False,
            )
        ]
        gen = ChangelogGenerator()
        output = gen.generate()

        assert "### Bug Fixes" in output
        assert "fix crash" in output

    @patch.object(ChangelogGenerator, "_parse_commits")
    def test_generate_groups_docs_into_documentation(self, mock_parse):
        mock_parse.return_value = [
            ChangelogEntry(
                commit_hash="ccc3333",
                commit_type="docs",
                scope="",
                description="update guide",
                breaking=False,
            )
        ]
        gen = ChangelogGenerator()
        output = gen.generate()

        assert "### Documentation" in output
        assert "update guide" in output

    @patch.object(ChangelogGenerator, "_parse_commits")
    def test_generate_groups_refactor_into_refactoring(self, mock_parse):
        mock_parse.return_value = [
            ChangelogEntry(
                commit_hash="ddd4444",
                commit_type="refactor",
                scope="",
                description="simplify logic",
                breaking=False,
            )
        ]
        gen = ChangelogGenerator()
        output = gen.generate()

        assert "### Refactoring" in output

    @patch.object(ChangelogGenerator, "_parse_commits")
    def test_generate_groups_test_into_tests(self, mock_parse):
        mock_parse.return_value = [
            ChangelogEntry(
                commit_hash="eee5555",
                commit_type="test",
                scope="",
                description="add coverage",
                breaking=False,
            )
        ]
        gen = ChangelogGenerator()
        output = gen.generate()

        assert "### Tests" in output

    @patch.object(ChangelogGenerator, "_parse_commits")
    def test_generate_groups_style_and_chore_into_chores(self, mock_parse):
        mock_parse.return_value = [
            ChangelogEntry(
                commit_hash="fff6666",
                commit_type="style",
                scope="",
                description="fix lint",
                breaking=False,
            ),
            ChangelogEntry(
                commit_hash="ggg7777",
                commit_type="chore",
                scope="deps",
                description="bump deps",
                breaking=False,
            ),
        ]
        gen = ChangelogGenerator()
        output = gen.generate()

        assert "### Chores" in output
        assert "fix lint" in output
        assert "bump deps" in output

    @patch.object(ChangelogGenerator, "_parse_commits")
    def test_generate_omits_empty_sections(self, mock_parse):
        mock_parse.return_value = [
            ChangelogEntry(
                commit_hash="hhh8888",
                commit_type="feat",
                scope="",
                description="only feature",
                breaking=False,
            )
        ]
        gen = ChangelogGenerator()
        output = gen.generate()

        assert "### Features" in output
        # Other sections should not appear when empty
        assert "### Bug Fixes" not in output
        assert "### Documentation" not in output
        assert "### Refactoring" not in output
        assert "### Tests" not in output

    @patch.object(ChangelogGenerator, "_parse_commits")
    def test_generate_includes_version_header(self, mock_parse):
        mock_parse.return_value = []
        gen = ChangelogGenerator()
        output = gen.generate()

        # The version header line should start with "## "
        # get_version() reads from pyproject.toml, which has "0.1.0"
        assert "## " in output

    @patch.object(ChangelogGenerator, "_parse_commits")
    def test_generate_empty_commits_produces_header_only(self, mock_parse):
        mock_parse.return_value = []
        gen = ChangelogGenerator()
        output = gen.generate()

        lines = [l for l in output.split("\n") if l.strip()]
        # Only the version header line should remain
        assert len(lines) == 1
        assert lines[0].startswith("## ")

    @patch.object(ChangelogGenerator, "_parse_commits")
    def test_generate_multiple_entries_in_same_section(self, mock_parse):
        mock_parse.return_value = [
            ChangelogEntry("aaa1111", "feat", "", "feature A", False),
            ChangelogEntry("bbb2222", "feat", "core", "feature B", False),
        ]
        gen = ChangelogGenerator()
        output = gen.generate()

        assert "feature A" in output
        assert "feature B" in output
        # Only one Features section header
        assert output.count("### Features") == 1


# ---------------------------------------------------------------------------
# ChangelogGenerator _parse_commits
# ---------------------------------------------------------------------------


class TestChangelogGeneratorParseCommits:
    """Tests for ChangelogGenerator._parse_commits() via mocked subprocess."""

    def _make_mock_result(self, stdout: str, returncode: int = 0) -> MagicMock:
        result = MagicMock()
        result.stdout = stdout
        result.returncode = returncode
        return result

    @patch("subprocess.run")
    def test_parse_commits_extracts_conventional_commits(self, mock_run):
        stdout = "a1b2c3d feat(api): add endpoint\nb2c3d4e fix: resolve null\n"
        mock_run.return_value = self._make_mock_result(stdout)

        gen = ChangelogGenerator()
        entries = gen._parse_commits("HEAD~5", "HEAD")

        assert len(entries) == 2
        assert entries[0].commit_hash == "a1b2c3d"
        assert entries[0].commit_type == "feat"
        assert entries[0].scope == "api"
        assert entries[0].description == "add endpoint"
        assert entries[1].commit_type == "fix"

    @patch("subprocess.run")
    def test_parse_commits_skips_non_conventional(self, mock_run):
        stdout = "a1b2c3d Merge pull request #42\nb2c3d4e feat: new thing\n"
        mock_run.return_value = self._make_mock_result(stdout)

        gen = ChangelogGenerator()
        entries = gen._parse_commits("HEAD~5", "HEAD")

        assert len(entries) == 1
        assert entries[0].commit_type == "feat"

    @patch("subprocess.run")
    def test_parse_commits_detects_breaking_via_keyword(self, mock_run):
        """Breaking is detected when "BREAKING" appears in the commit message."""
        stdout = "a1b2c3d feat(api): BREAKING API overhaul\n"
        mock_run.return_value = self._make_mock_result(stdout)

        gen = ChangelogGenerator()
        entries = gen._parse_commits("HEAD~5", "HEAD")

        assert len(entries) == 1
        assert entries[0].breaking is True

    @patch("subprocess.run")
    def test_parse_commits_empty_output(self, mock_run):
        mock_run.return_value = self._make_mock_result("")

        gen = ChangelogGenerator()
        entries = gen._parse_commits("HEAD~5", "HEAD")

        assert entries == []

    @patch("subprocess.run")
    def test_parse_commits_git_failure_returns_empty(self, mock_run):
        mock_run.return_value = self._make_mock_result("", returncode=128)

        gen = ChangelogGenerator()
        entries = gen._parse_commits("HEAD~5", "HEAD")

        assert entries == []

    @patch("subprocess.run", side_effect=FileNotFoundError("git not found"))
    def test_parse_commits_git_not_installed(self, mock_run):
        gen = ChangelogGenerator()
        entries = gen._parse_commits("HEAD~5", "HEAD")

        assert entries == []

    @patch("subprocess.run")
    def test_parse_commits_skips_hash_only_lines(self, mock_run):
        """Lines with only a hash (no message) are skipped."""
        stdout = "a1b2c3d\nb2c3d4e feat: real commit\n"
        mock_run.return_value = self._make_mock_result(stdout)

        gen = ChangelogGenerator()
        entries = gen._parse_commits("HEAD~5", "HEAD")

        assert len(entries) == 1
        assert entries[0].description == "real commit"

    @patch("subprocess.run")
    def test_parse_commits_uses_correct_refs(self, mock_run):
        """git log is called with the correct from..to ref range."""
        mock_run.return_value = self._make_mock_result("")

        gen = ChangelogGenerator()
        gen._parse_commits("v0.1.0", "v0.2.0")

        args = mock_run.call_args[0][0]
        assert args == ["git", "log", "--oneline", "v0.1.0..v0.2.0"]


# ---------------------------------------------------------------------------
# Version: get_version()
# ---------------------------------------------------------------------------


class TestGetVersion:
    """Tests for get_version() reading from pyproject.toml."""

    def test_get_version_reads_pyproject(self):
        """get_version returns the version from the real pyproject.toml."""
        version = get_version()
        # The actual project version in pyproject.toml is "0.1.0"
        assert version == "0.1.0"

    def test_get_version_returns_string(self):
        version = get_version()
        assert isinstance(version, str)

    @patch("midas.release.version._VERSION_FILES")
    def test_get_version_missing_pyproject_returns_unknown(self, mock_files):
        """When pyproject.toml does not exist, returns fallback marker."""
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_files.__getitem__ = MagicMock(return_value=mock_path)

        version = get_version()
        assert version == "0.0.0-unknown"


# ---------------------------------------------------------------------------
# Version: validate_version_consistency()
# ---------------------------------------------------------------------------


class TestValidateVersionConsistency:
    """Tests for validate_version_consistency()."""

    def test_consistency_with_real_files(self):
        """Consistency check passes when pyproject.toml and __init__.py agree."""
        result = validate_version_consistency()
        assert result["consistent"] is True
        assert result["pyproject.toml"] == "0.1.0"
        assert result["src/midas/__init__.py"] == "0.1.0"

    def test_consistency_returns_dict_with_required_keys(self):
        result = validate_version_consistency()
        assert "consistent" in result
        assert "pyproject.toml" in result

    @patch("midas.release.version.get_version")
    def test_consistency_detects_mismatch(self, mock_get_version):
        """Consistency check fails when versions differ across files."""
        mock_get_version.return_value = "9.9.9"

        # __init__.py still has "0.1.0", pyproject reports "9.9.9"
        result = validate_version_consistency()

        assert result["consistent"] is False
        assert result["pyproject.toml"] == "9.9.9"
        # __init__.py still reads "0.1.0" from disk
        assert result["src/midas/__init__.py"] == "0.1.0"

    @patch("midas.release.version.get_version", return_value="0.1.0")
    def test_consistency_missing_init_file(self, mock_get_version):
        """Consistency check fails when __init__.py is missing."""
        init_path = MagicMock()
        init_path.exists.return_value = False

        fake_files = {
            "pyproject.toml": Path("pyproject.toml"),
            "src/midas/__init__.py": init_path,
        }

        with patch("midas.release.version._VERSION_FILES", fake_files):
            result = validate_version_consistency()

        assert result["consistent"] is False
        assert result["src/midas/__init__.py"] == "FILE_NOT_FOUND"

    @patch("midas.release.version.get_version", return_value="0.1.0")
    def test_consistency_version_not_found_in_init(self, mock_get_version):
        """Consistency check fails when __init__.py has no __version__ assignment."""
        init_path = MagicMock()
        init_path.exists.return_value = True
        # File exists but contains no __version__ pattern
        init_path.read_text.return_value = '"""No version here."""\n'

        fake_files = {
            "pyproject.toml": Path("pyproject.toml"),
            "src/midas/__init__.py": init_path,
        }

        with patch("midas.release.version._VERSION_FILES", fake_files):
            result = validate_version_consistency()

        assert result["consistent"] is False
        assert result["src/midas/__init__.py"] == "VERSION_NOT_FOUND"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: pre-release versions, unusual commit formats, etc."""

    def test_changelog_entry_with_empty_description(self):
        """Entry with empty description still formats without error."""
        entry = ChangelogEntry(
            commit_hash="abcdef123456",
            commit_type="chore",
            scope="",
            description="",
            breaking=False,
        )
        result = entry.format()
        # Should produce "-  (abcdef1)" — empty description between dash and hash
        assert "(abcdef1)" in result

    def test_commit_pattern_with_long_description(self):
        """Pattern handles multi-word descriptions."""
        desc = "add support for complex query builder with chaining"
        match = _COMMIT_PATTERN.match(f"feat(query): {desc}")
        assert match is not None
        assert match.group("description") == desc

    def test_commit_pattern_scope_with_numbers(self):
        """Scope can contain digits."""
        match = _COMMIT_PATTERN.match("fix(api2): fix endpoint")
        assert match is not None
        assert match.group("scope") == "api2"

    @patch("subprocess.run")
    def test_parse_commits_all_types_in_sections(self, mock_run):
        """Every recognized commit type maps to a section."""
        lines = [
            "a1 feat: f1",
            "b2 fix: f2",
            "c3 docs: f3",
            "d4 refactor: f4",
            "e5 test: f5",
            "f6 style: f6",
            "g7 chore: f7",
        ]
        mock_run.return_value = MagicMock(stdout="\n".join(lines) + "\n", returncode=0)

        gen = ChangelogGenerator()
        with patch.object(gen, "_version", "1.0.0"):
            output = gen.generate()

        assert "### Features" in output
        assert "### Bug Fixes" in output
        assert "### Documentation" in output
        assert "### Refactoring" in output
        assert "### Tests" in output
        assert "### Chores" in output

    def test_version_string_is_semver_like(self):
        """The real version string looks like semver (MAJOR.MINOR.PATCH)."""
        version = get_version()
        parts = version.split(".")
        assert len(parts) >= 2  # At minimum major.minor
        # All parts before any pre-release suffix should be numeric
        for part in parts:
            # Allow pre-release suffix on the last part (e.g., "0rc1")
            numeric_part = part.split("-")[0].split("a")[0].split("b")[0].split("rc")[0]
            assert numeric_part.isdigit(), f"Version part '{part}' is not numeric"

    @patch("subprocess.run")
    def test_parse_commits_mixed_conventional_and_non(self, mock_run):
        """Only conventional commits are parsed; others are silently skipped."""
        stdout = (
            "a1 feat(auth): add login\n"
            "a2 Merge branch 'main'\n"
            "a3 fix: null pointer\n"
            "a4 WIP: work in progress\n"
            "a5 chore(deps): bump pytest\n"
        )
        mock_run.return_value = MagicMock(stdout=stdout, returncode=0)

        gen = ChangelogGenerator()
        entries = gen._parse_commits("HEAD~10", "HEAD")

        types = [e.commit_type for e in entries]
        assert types == ["feat", "fix", "chore"]
        assert len(entries) == 3

    @patch("subprocess.run")
    def test_generate_breaking_entry_included_in_output(self, mock_run):
        """Breaking entries are formatted with BREAKING marker in output."""
        mock_run.return_value = MagicMock(
            stdout="a1b2c3d feat: BREAKING API overhaul\n", returncode=0
        )

        gen = ChangelogGenerator()
        output = gen.generate()

        assert "**BREAKING**" in output
        assert "BREAKING API overhaul" in output
