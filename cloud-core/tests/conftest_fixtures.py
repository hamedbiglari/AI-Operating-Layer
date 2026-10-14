"""Real document fixtures, generated deterministically at test time.

Generated rather than committed as binaries so the corpus is reproducible
and reviewable: a reader can see exactly what is in each file.
"""
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()
