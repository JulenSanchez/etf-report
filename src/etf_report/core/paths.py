from __future__ import annotations

from pathlib import Path


def _find_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "config").is_dir() and (parent / "scripts").is_dir():
            return parent
    return current.parents[3]


PROJECT_ROOT = _find_project_root()
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
RESEARCH_DIR = PROJECT_ROOT / "research"
ASSETS_DIR = PROJECT_ROOT / "assets"
INDEX_HTML = PROJECT_ROOT / "index.html"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

