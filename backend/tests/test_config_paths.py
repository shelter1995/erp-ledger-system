from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from app.config import ROOT_DIR


def test_import_dir_environment_selects_controlled_workbook_directory(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["IMPORT_DIR"] = str(tmp_path)

    result = subprocess.run(
        [sys.executable, "-c", "from app.config import DOCS_DIR; print(DOCS_DIR)"],
        cwd=ROOT_DIR / "backend",
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert Path(result.stdout.strip()) == tmp_path.resolve()
