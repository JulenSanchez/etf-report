"""Legacy rule setup notice.

etf-report no longer installs active project rules. Use AGENTS.md for cold start
and docs/ai/AGENT_GUIDE.md for detailed AI collaboration notes.

Usage:
  python scripts/setup_rules.py
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_RULES_DIR = PROJECT_ROOT / "docs" / "ai" / "legacy" / "rules"


def main() -> int:
    print("etf-report no longer installs active .codebuddy/.claude project rules.")
    print("Current agent entry: AGENTS.md")
    print("Detailed guide: docs/ai/AGENT_GUIDE.md")
    print(f"Legacy rule archive: {LEGACY_RULES_DIR}")
    print("No files were copied or installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
