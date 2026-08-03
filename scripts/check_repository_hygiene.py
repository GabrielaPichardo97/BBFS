"""Fail when public-repository paths contain secrets or generated production data."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

GENERATED_ROOTS = (
    "artifacts",
    "data/bronze",
    "data/cache",
    "data/gold",
    "data/models",
    "models",
)
ALLOWED_RUNTIME_MARKERS = frozenset({"artifacts/.gitkeep", "data/.gitkeep"})
PROHIBITED_SUFFIXES = frozenset(
    {".db", ".duckdb", ".faiss", ".index", ".onnx", ".pt", ".pth", ".safetensors"}
)
SKIPPED_FILESYSTEM_PARTS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "htmlcov",
        "tmp",
    }
)
SECRET_PATTERNS = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    (
        "github_token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    ),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
)
SYNTHETIC_MARKER = re.compile(
    r"[\"']source_type[\"']\s*:\s*[\"']synthetic[\"']|"
    r"source_type\s*=\s*[\"']synthetic[\"']",
    re.IGNORECASE,
)
MAX_TEXT_BYTES = 1_000_000


def tracked_paths(root: Path, *, include_untracked: bool = False) -> list[Path]:
    """Return tracked paths and, optionally, untracked non-ignored paths."""
    command = ["git", "-C", str(root), "ls-files", "-z"]
    if include_untracked:
        command.extend(("--cached", "--others", "--exclude-standard"))
    process = subprocess.run(
        command,
        check=False,
        capture_output=True,
    )
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git ls-files failed: {detail}")
    return [Path(item.decode("utf-8")) for item in process.stdout.split(b"\0") if item]


def filesystem_paths(root: Path) -> list[Path]:
    """Return files visible in a clean checkout while skipping local tool caches."""
    paths: list[Path] = []
    for directory, subdirectories, filenames in os.walk(root):
        subdirectories[:] = [
            name for name in subdirectories if name not in SKIPPED_FILESYSTEM_PARTS
        ]
        directory_path = Path(directory)
        paths.extend((directory_path / name).relative_to(root) for name in filenames)
    return paths


def scan_repository(root: Path, relative_paths: Iterable[Path]) -> list[str]:
    """Report violations without ever printing a possible secret value."""
    violations: list[str] = []
    for relative in relative_paths:
        normalized = relative.as_posix()
        if normalized.startswith("./"):
            normalized = normalized[2:]
        path = root / relative
        if normalized in ALLOWED_RUNTIME_MARKERS:
            continue
        if _under_generated_root(normalized):
            violations.append(f"generated runtime file: {normalized}")
        if relative.suffix.lower() in PROHIBITED_SUFFIXES:
            violations.append(f"database/model/index file: {normalized}")
        if _credential_filename(relative):
            violations.append(f"credential-like filename: {normalized}")
        text = _small_text(path)
        if text is None:
            continue
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                violations.append(f"{label} signature: {normalized}")
        if _under_generated_root(normalized) and SYNTHETIC_MARKER.search(text):
            violations.append(f"synthetic production record: {normalized}")
    return sorted(set(violations))


def _under_generated_root(relative: str) -> bool:
    return any(relative == root or relative.startswith(f"{root}/") for root in GENERATED_ROOTS)


def _credential_filename(relative: Path) -> bool:
    name = relative.name.lower()
    if name == ".env.example":
        return False
    return (
        name == ".env"
        or name.startswith("credentials")
        or relative.suffix.lower() in {".key", ".pem", ".p12", ".pfx"}
    )


def _small_text(path: Path) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_TEXT_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--mode",
        choices=("tracked", "publishable", "filesystem"),
        default="tracked",
    )
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    try:
        if arguments.mode == "filesystem":
            paths = filesystem_paths(root)
        else:
            paths = tracked_paths(root, include_untracked=arguments.mode == "publishable")
        violations = scan_repository(root, paths)
    except RuntimeError as error:
        print(f"repository-hygiene: ERROR: {error}", file=sys.stderr)
        return 2
    if violations:
        for violation in violations:
            print(f"repository-hygiene: FAIL: {violation}", file=sys.stderr)
        return 1
    print(f"repository-hygiene: PASS ({len(paths)} files, mode={arguments.mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
