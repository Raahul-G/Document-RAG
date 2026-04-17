"""
Dev launch helper.
Run: source .venv/bin/activate && uvicorn backend.main:app --reload
"""
import subprocess
import sys


if __name__ == "__main__":
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--reload"],
        check=True,
    )
