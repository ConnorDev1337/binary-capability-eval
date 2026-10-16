"""Guards on what this repository is allowed to contain.

The threat model promises that no binaries are committed and that sources contain no
hidden characters. These tests keep those promises checked in CI.
"""

from __future__ import annotations

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


def _files(root: Path) -> list[Path]:
    out = []
    for p in root.rglob("*"):
        if p.is_file() and not any(
            part in SKIP_DIRS or part.endswith(".egg-info") for part in p.relative_to(root).parts
        ):
            out.append(p)
    return out


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
    shipped = [
        p for p in (repo_root / "challenges").rglob("*") if p.is_file() and p.name != "README.md"
    ]
    assert not shipped, f"challenges/ must ship empty: {shipped}"
