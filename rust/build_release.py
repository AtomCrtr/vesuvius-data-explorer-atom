"""Build the optional wheel with the Python interpreter that will use it."""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    manifest = Path(__file__).with_name("Cargo.toml").resolve()
    subprocess.run(
        [sys.executable, "-m", "maturin", "build", "--release", "--locked",
         "--manifest-path", str(manifest), "--interpreter", sys.executable],
        check=True,
    )
