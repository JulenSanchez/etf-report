"""Validate research/pool/README.md Current Best table against config/quant_universe.yaml.
Usage: python scripts/validate_pool_docs.py
Exit 0 = in sync, Exit 1 = mismatch found.
"""
import sys, re, yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG = PROJECT_ROOT / "config" / "quant_universe.yaml"
POOL_README = PROJECT_ROOT / "research" / "pool" / "README.md"

if not POOL_README.exists():
    print(f"SKIP: {POOL_README} not found")
    sys.exit(0)

# Read config pool
with open(CONFIG, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
config_codes = {e["code"]: e["name"] for e in cfg.get("universe", [])}

# Parse Current Best table from README
text = POOL_README.read_text(encoding="utf-8")
in_table = False
readme_codes = {}
for line in text.split("\n"):
    if "Current Best" in line:
        in_table = True
        continue
    if in_table:
        if line.startswith("##") or line.startswith("---"):
            break
        if line.startswith("|") and not line.startswith("| ETF"):
            cells = [c.strip() for c in line.split("|")]
            if len(cells) >= 4 and cells[2] and cells[2] != "代码":
                try:
                    code = cells[2]
                    name = cells[1] if len(cells) > 1 else ""
                    if re.match(r"^\d{6}$", code):
                        readme_codes[code] = name
                except (ValueError, IndexError):
                    pass

# Compare
errors = []
for code, name in sorted(config_codes.items()):
    if code not in readme_codes:
        errors.append(f"config has {code} {name} — NOT in research/pool README")
for code, name in sorted(readme_codes.items()):
    if code not in config_codes:
        errors.append(f"research/pool README has {code} {name} — NOT in config")

if errors:
    print(f"POOL DOCS OUT OF SYNC ({len(errors)} issues):")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)

print(f"OK: research/pool/README.md in sync ({len(config_codes)} ETFs)")
