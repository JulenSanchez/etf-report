#!/usr/bin/env python3
from __future__ import annotations

import runpy
import sys
from pathlib import Path

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config").is_dir() and (parent / "scripts").is_dir())
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

if __name__ == "__main__":
    runpy.run_path(str(SCRIPTS_DIR / "quant_data_fetcher.py"), run_name="__main__")
