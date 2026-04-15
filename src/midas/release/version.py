"""
Version management for Midas releases.

Ensures version consistency across all declared locations
(pyproject.toml, __init__.py) per zero-tolerance Rule 5.

Ref: rules/zero-tolerance.md Rule 5
"""

import re
import tomllib
from pathlib import Path

# Project root directory.
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# Files that MUST contain the same version string.
_VERSION_FILES = {
    "pyproject.toml": _PROJECT_ROOT / "pyproject.toml",
    "src/midas/__init__.py": _PROJECT_ROOT / "src" / "midas" / "__init__.py",
}

_VERSION_PATTERN = re.compile(r'__version__\s*=\s*["\']([^"\']+)["\']')


def get_version() -> str:
    """Read the current version from pyproject.toml.

    Returns
    -------
    str
        The version string (e.g. "0.1.0").
    """
    pyproject_path = _VERSION_FILES["pyproject.toml"]
    if not pyproject_path.exists():
        return "0.0.0-unknown"

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    version = data.get("project", {}).get("version", "0.0.0-unknown")
    return str(version)


def validate_version_consistency() -> dict[str, str | bool]:
    """Validate that all version locations agree.

    Returns
    -------
    dict
        Result with 'consistent' bool and per-file versions.
    """
    pyproject_version = get_version()
    results: dict[str, str | bool] = {
        "pyproject.toml": pyproject_version,
        "consistent": True,
    }

    for name, path in _VERSION_FILES.items():
        if name == "pyproject.toml":
            continue

        if not path.exists():
            results[name] = "FILE_NOT_FOUND"
            results["consistent"] = False
            continue

        content = path.read_text()
        match = _VERSION_PATTERN.search(content)
        if match:
            file_version = match.group(1)
            results[name] = file_version
            if file_version != pyproject_version:
                results["consistent"] = False
        else:
            results[name] = "VERSION_NOT_FOUND"
            results["consistent"] = False

    return results
