"""
Changelog generation for Midas releases.

Generates structured changelogs from git history following
conventional commit format.

Ref: rules/git.md (conventional commits)
"""

import re
import subprocess
from dataclasses import dataclass

from midas.release.version import get_version

_COMMIT_PATTERN = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|test|chore)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r":\s*(?P<description>.+)$"
)

# Strict allowlist for git refs: branch names, tags, commit hashes, HEAD, and
# relative refs. Rejects any ref starting with '-' (prevents flag injection).
_GIT_REF_REGEX = re.compile(r"^[a-zA-Z0-9_./^~:]+$")


@dataclass
class ChangelogEntry:
    """A single changelog entry."""

    commit_hash: str
    commit_type: str
    scope: str
    description: str
    breaking: bool = False

    def format(self) -> str:
        """Format as markdown list item."""
        prefix = "**BREAKING** " if self.breaking else ""
        scope = f"**{self.scope}**: " if self.scope else ""
        return f"- {prefix}{scope}{self.description} ({self.commit_hash[:7]})"


class ChangelogGenerator:
    """Generates changelogs from git history."""

    def __init__(self) -> None:
        self._version = get_version()

    def generate(self, from_ref: str = "HEAD~20", to_ref: str = "HEAD") -> str:
        """Generate changelog from git history.

        Parameters
        ----------
        from_ref:
            Starting git reference.
        to_ref:
            Ending git reference.

        Returns
        -------
        str
            Markdown changelog.
        """
        entries = self._parse_commits(from_ref, to_ref)

        sections: dict[str, list[ChangelogEntry]] = {
            "Features": [],
            "Bug Fixes": [],
            "Documentation": [],
            "Refactoring": [],
            "Tests": [],
            "Chores": [],
        }

        type_map = {
            "feat": "Features",
            "fix": "Bug Fixes",
            "docs": "Documentation",
            "refactor": "Refactoring",
            "test": "Tests",
            "style": "Chores",
            "chore": "Chores",
        }

        for entry in entries:
            section = type_map.get(entry.commit_type, "Chores")
            sections[section].append(entry)

        lines = [f"## {self._version}", ""]
        for section_name, section_entries in sections.items():
            if not section_entries:
                continue
            lines.append(f"### {section_name}")
            lines.append("")
            for entry in section_entries:
                lines.append(entry.format())
            lines.append("")

        return "\n".join(lines)

    def _parse_commits(self, from_ref: str, to_ref: str) -> list[ChangelogEntry]:
        """Parse git log into changelog entries."""
        # Validate refs against allowlist to prevent flag injection
        if not _GIT_REF_REGEX.match(from_ref) or not _GIT_REF_REGEX.match(to_ref):
            return []
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", f"{from_ref}..{to_ref}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return []
        except FileNotFoundError:
            return []

        entries = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split(" ", 1)
            if len(parts) < 2:
                continue
            commit_hash = parts[0]
            message = parts[1]

            match = _COMMIT_PATTERN.match(message)
            if match:
                entries.append(
                    ChangelogEntry(
                        commit_hash=commit_hash,
                        commit_type=match.group("type"),
                        scope=match.group("scope") or "",
                        description=match.group("description"),
                        breaking="BREAKING" in message,
                    )
                )

        return entries
