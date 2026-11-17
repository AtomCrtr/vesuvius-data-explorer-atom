"""The core must run without loading any optional GUI packages."""

import subprocess
import sys


def test_core_imports_without_gui():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
import vesuvius_data_explorer.core
import vesuvius_data_explorer.core.demo
import vesuvius_data_explorer.core.surface
import vesuvius_data_explorer.core.volume

for name in sys.modules:
    assert name.split('.')[0] not in {
        'streamlit', 'matplotlib', 'napari', 'qtpy', 'PyQt5', 'PyQt6', 'PySide6'
    }, name
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
