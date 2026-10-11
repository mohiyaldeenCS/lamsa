"""Launch the LAMSA application from the repository root."""
from pathlib import Path
import runpy
import sys

if __name__ == "__main__":
    project = Path(__file__).resolve().parent / "perfume_project"
    sys.path.insert(0, str(project))
    runpy.run_path(str(project / "app.py"), run_name="__main__")
