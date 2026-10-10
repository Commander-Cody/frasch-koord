"""files.py: the lock a read-modify-write run of the name list holds."""

from __future__ import annotations

import pytest

from frasch import files
from frasch.errors import PipelineError
from frasch.paths import Workspace


def test_lock_is_exclusive(ws: Workspace) -> None:
    with files.lock(ws.lock):
        with pytest.raises(PipelineError, match="another `frasch match`"):
            with files.lock(ws.lock):
                pass
    with files.lock(ws.lock):  # released again
        pass
