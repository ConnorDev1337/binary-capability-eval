from __future__ import annotations

from pathlib import Path

import pytest

from bineval.rubric import Attempt, RubricStep

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = REPO_ROOT / "examples"


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def example_challenge_path() -> Path:
    return EXAMPLES / "asm-reading-001.yaml"


def make_attempt(
    cid: str = "c1",
    *,
    level: str = "ASM_READING",
    model: str = "m",
    run: int = 0,
    solved: bool = False,
    step: RubricStep | None = None,
) -> Attempt:
    if step is None:
        step = RubricStep.DELIVER if solved else RubricStep.READ_ASSEMBLY
    return Attempt(
        challenge_id=cid,
        level=level,
        model=model,
        run_index=run,
        solved=solved,
        furthest_step=step,
    )
