"""Resolve all application paths independently of the shell's working directory."""
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parent
DATA = APP / 'data'
PYTHON = ROOT / '.venv-cu130/Scripts/python.exe'
HARNESS = APP / 'agent/harness.mjs'
