from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STARTER = ROOT / "benchmarks" / "starter"


@pytest.fixture
def starter() -> Path:
    return STARTER


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def tiny_task(tmp_path: Path) -> Path:
    """A minimal task: add() subtracts instead of adding."""
    root = tmp_path / "tiny"
    _write(root / "task.yaml", "id: tiny\ntitle: add is broken\ninstruction: add(2, 3) returns -1, expected 5.\n")
    _write(root / "repo" / "pytest.ini", "[pytest]\ntestpaths = tests\n")
    _write(root / "repo" / "calc.py", "def add(a, b):\n    return a - b\n")
    _write(root / "repo" / "tests" / "test_calc.py", "from calc import add\n\n\ndef test_zero():\n    assert add(0, 0) == 0\n")
    _write(root / "hidden_tests" / "tests" / "test_calc_hidden.py",
           "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n")
    _write(root / "solution" / "calc.py", "def add(a, b):\n    return a + b\n")
    return root
