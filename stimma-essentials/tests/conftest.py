"""Run the pack's tests against a stimma backend checkout.

The backend is found via ``STIMMA_BACKEND`` or the sibling ``stimma/backend``
checkout. Its virtualenv supplies pytest, Pillow and numpy; run with
``<backend>/.venv/bin/python -m pytest tests`` from this directory.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PACK = Path(__file__).resolve().parents[1]
BACKEND = Path(os.environ.get("STIMMA_BACKEND") or PACK.parents[1] / "stimma" / "backend")
if not (BACKEND / "packages" / "recipes.py").is_file():
    raise RuntimeError(f"stimma backend not found at {BACKEND}; set STIMMA_BACKEND")

for entry in (str(BACKEND), str(PACK / "skills" / "packaging" / "lib")):
    if entry not in sys.path:
        sys.path.insert(0, entry)


@pytest.fixture(scope="session", autouse=True)
def this_pack_recipes():
    """Make this pack's ``recipes/*.py`` visible to ``get_recipe``/``list_recipes``."""
    from agent.v2 import stimpacks as stimpacks_mod

    def only_this_pack(profile_id=None):
        return [(PACK.name, p) for p in sorted((PACK / "recipes").glob("*.py")) if not p.name.startswith("_")]

    with patch.object(stimpacks_mod, "list_stimpack_recipe_files", only_this_pack):
        yield
