"""Guards on what this repository is allowed to contain.

The threat model promises that no binaries are committed and that sources contain no
hidden characters. These tests keep those promises checked in CI.

They check the files git would commit (tracked, plus untracked files that are not
ignored), not the whole working tree: private challenges and the binaries built for them
live in ignored paths inside a lab checkout, and must not make the suite fail there.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
}

# Magic numbers of executable / object formats that must never be committed.
EXECUTABLE_MAGIC = {
    bytes.fromhex("7f454c46"): "ELF",
    bytes.fromhex("4d5a"): "PE/DOS",
    bytes.fromhex("cffaedfe"): "Mach-O 64",
    bytes.fromhex("cefaedfe"): "Mach-O 32",
    bytes.fromhex("cafebabe"): "Mach-O universal",
}

# Built from code points so this file does not itself contain the characters it bans.
HIDDEN_CHARS = {
    chr(0x200B): "ZERO WIDTH SPACE",
    chr(0x200C): "ZERO WIDTH NON-JOINER",
    chr(0x200D): "ZERO WIDTH JOINER",
    chr(0x2060): "WORD JOINER",
    chr(0xFEFF): "BYTE ORDER MARK",
    chr(0x202E): "RIGHT-TO-LEFT OVERRIDE",
    chr(0x202D): "LEFT-TO-RIGHT OVERRIDE",
}

TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".toml", ".jsonl", ".json", ".txt", ".cfg"}


def _git_files(root: Path) -> list[Path] | None:
    git = shutil.which("git")
    if git is None or not (root / ".git").exists():
        return None
    try:
        listing = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [git, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError):
        return None
    # --cached still lists files deleted from the working tree but not yet staged.
    return sorted(p for p in {root / n for n in listing.split("\0") if n} if p.is_file())


def _walk_files(root: Path) -> list[Path]:
    # Fallback for CI images without git and for unpacked sdists. Both are clean
    # checkouts, so there are no ignored local files to tell apart.
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file()
        and not any(
            part in SKIP_DIRS or part.endswith(".egg-info") for part in p.relative_to(root).parts
        )
    )


def _files(root: Path) -> list[Path]:
    files = _git_files(root)
    return files if files is not None else _walk_files(root)


def test_no_executables_committed(repo_root):
    offenders = []
    for p in _files(repo_root):
        head = p.read_bytes()[:4]
        for magic, name in EXECUTABLE_MAGIC.items():
            if head.startswith(magic):
                offenders.append(f"{p.relative_to(repo_root)} ({name})")
    assert not offenders, f"executable files must not be committed: {offenders}"


@pytest.mark.parametrize("suffix", sorted(TEXT_SUFFIXES))
def test_no_hidden_characters(repo_root, suffix):
    offenders = []
    for p in _files(repo_root):
        if p.suffix != suffix:
            continue
        text = p.read_text(encoding="utf-8")
        for ch, name in HIDDEN_CHARS.items():
            if ch in text:
                offenders.append(f"{p.relative_to(repo_root)}: {name}")
    assert not offenders, f"hidden characters found: {offenders}"


def test_no_challenges_shipped(repo_root):
    challenges = repo_root / "challenges"
    shipped = [
        p.relative_to(repo_root)
        for p in _files(repo_root)
        if p.is_relative_to(challenges) and p != challenges / "README.md"
    ]
    assert not shipped, f"challenges/ must ship empty: {shipped}"


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_ignored_lab_files_are_not_checked(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)  # noqa: S607
    (tmp_path / ".gitignore").write_text("challenges/*\n!challenges/README.md\n", encoding="utf-8")
    (tmp_path / "challenges" / "bin").mkdir(parents=True)
    (tmp_path / "challenges" / "README.md").write_text("x\n", encoding="utf-8")
    (tmp_path / "challenges" / "private.yaml").write_text("id: p\n", encoding="utf-8")
    (tmp_path / "challenges" / "bin" / "toy").write_bytes(bytes.fromhex("7f454c46") + b"\0")
    names = {p.relative_to(tmp_path).as_posix() for p in _files(tmp_path)}
    assert names == {".gitignore", "challenges/README.md"}
