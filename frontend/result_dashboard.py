"""Compatible entry point for the read-only research dashboard."""
from pathlib import Path
import sys

FRONTEND_DIR = Path(__file__).resolve().parent
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from research.app import main

main()
