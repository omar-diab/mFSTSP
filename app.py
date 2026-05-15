"""
Root entry point for Streamlit Community Cloud.

This file lets you deploy the app using:

    Main file path: app.py

It simply runs the real dashboard located at:
    frontend/result_dashboard.py
"""

from pathlib import Path
import runpy

DASHBOARD_PATH = Path(__file__).resolve().parent / "frontend" / "result_dashboard.py"

if not DASHBOARD_PATH.exists():
    raise FileNotFoundError(
        f"Dashboard file not found: {DASHBOARD_PATH}\n"
        "Make sure the frontend folder exists and contains result_dashboard.py."
    )

runpy.run_path(str(DASHBOARD_PATH), run_name="__main__")
