#!/usr/bin/env python3
"""Compatibility wrapper for quant payload generation.

The current official payload path is:
  update_report.py -> generate_quant_baseline_payload()

That path reads quant_universe.yaml through quant_contract.py and calls the
Tuner /api/run endpoint to build the 1Y/3Y payload consumed by index.html.

This file remains as a CLI entry point for users and automation that still run
`python scripts/quant_build_payload.py`, but it no longer owns a separate
quant_templates.yaml based pipeline.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from update_report import generate_quant_baseline_payload


def main():
    print("=" * 60)
    print("Quant payload builder")
    print("Official path: update_report.generate_quant_baseline_payload()")
    print("Requires Tuner running at http://localhost:5179")
    print("=" * 60)
    output = generate_quant_baseline_payload()
    print(f"Payload written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
