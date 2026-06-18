from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config").is_dir() and (parent / "scripts").is_dir())
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from etf_report.core import compliance_filter as _impl


if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
