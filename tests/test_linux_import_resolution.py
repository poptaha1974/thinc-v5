from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_project_test_and_script_packages_win_over_foreign_tests_package(
    tmp_path: Path,
) -> None:
    for package_name in ("tests", "scripts"):
        foreign_package = tmp_path / package_name
        foreign_package.mkdir()
        (foreign_package / "__init__.py").write_text("", encoding="utf-8")

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import tests.integration.api.test_assessments; "
                "import scripts.secret_scan"
            ),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
