# Root conftest: puts the repo root on sys.path for every pytest run, replacing
# the per-module sys.path.insert hacks. Runtime entry points use `python -m ...`
# from the repo root, where the cwd provides the same guarantee.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
