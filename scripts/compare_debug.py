"""
Compare debug_cli.json vs debug_tuner.json — pinpoint first divergence.
Usage: python scripts/compare_debug.py
"""
import json, sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CLI_PATH = SKILL_DIR / "data" / "debug_cli.json"
TUNER_PATH = SKILL_DIR / "data" / "debug_tuner.json"

def load(path):
    if not path.exists():
        print(f"[ERROR] File not found: {path}")
        sys.exit(1)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def main():
    cli_data = load(CLI_PATH)
    tuner_data = load(TUNER_PATH)
    cli_snaps = cli_data["snapshots"]
    tuner_snaps = tuner_data["snapshots"]

    print(f"CLI:   {len(cli_snaps)} snapshots")
    print(f"Tuner: {len(tuner_snaps)} snapshots")
    print()

    max_len = max(len(cli_snaps), len(tuner_snaps))
    first_diff = None
    categories = {"signal": 0, "px": 0, "holding": 0, "cash": 0, "nav_only": 0}

    for i in range(max_len):
        cli = cli_snaps[i] if i < len(cli_snaps) else None
        tuner = tuner_snaps[i] if i < len(tuner_snaps) else None

        if cli is None or tuner is None:
            print(f"[{i}] MISSING in {'CLI' if cli is None else 'Tuner'}")
            continue

        date = cli["signal_date"]
        issues = []

        # 1. Signal fields
        for field in ["regime", "total_target", "mu", "sigma", "hs300_above_ma"]:
            cv, tv = cli.get(field), tuner.get(field)
            if cv != tv:
                issues.append(f"  SIGNAL {field}: CLI={cv} vs Tuner={tv}")

        # 2. Top6 codes, scores, softmax, position, px
        cli_top6 = {e["code"]: e for e in cli.get("top6", [])}
        tuner_top6 = {e["code"]: e for e in tuner.get("top6", [])}
        c_codes, t_codes = set(cli_top6), set(tuner_top6)

        if c_codes != t_codes:
            issues.append(f"  CODES differ: +CLI={c_codes - t_codes} +Tuner={t_codes - c_codes}")

        for code in c_codes & t_codes:
            for sub in ["score", "softmax_w", "position"]:
                cv, tv = cli_top6[code].get(sub, 0), tuner_top6[code].get(sub, 0)
                if abs(cv - tv) > 0.0001:
                    issues.append(f"  {code}.{sub}: CLI={cv:.4f} vs Tuner={tv:.4f}")
            cp, tp = cli_top6[code].get("px", 0), tuner_top6[code].get("px", 0)
            if cp and tp and abs(cp - tp) > 0.001:
                issues.append(f"  {code}.px(top6): CLI={cp:.3f} vs Tuner={tp:.3f}")

        # 2b. All prices (including ETFs being sold)
        cli_apx = cli.get("all_px", {})
        tuner_apx = tuner.get("all_px", {})
        for code in set(cli_apx) | set(tuner_apx):
            cp, tp = cli_apx.get(code, 0), tuner_apx.get(code, 0)
            if cp and tp and abs(cp - tp) > 0.001:
                issues.append(f"  {code}.px(any): CLI={cp:.3f} vs Tuner={tp:.3f}")

        # 3. Holdings (shares)
        c_hold = cli.get("holdings", {})
        t_hold = tuner.get("holdings", {})
        c_hcodes, t_hcodes = set(c_hold), set(t_hold)
        for code in c_hcodes - t_hcodes:
            issues.append(f"  HOLD {code}: CLI={c_hold[code]} shares, Tuner=0")
        for code in t_hcodes - c_hcodes:
            issues.append(f"  HOLD {code}: CLI=0, Tuner={t_hold[code]} shares")
        for code in c_hcodes & t_hcodes:
            if abs(c_hold[code] - t_hold[code]) > 1e-6:
                issues.append(f"  HOLD {code}: CLI={c_hold[code]:.6f} vs Tuner={t_hold[code]:.6f}")

        # 4. Cash
        cc, tc = cli.get("cash", 0), tuner.get("cash", 0)
        if abs(cc - tc) > 0.5:
            issues.append(f"  CASH: CLI={cc:.2f} vs Tuner={tc:.2f} (diff={tc-cc:+.2f})")

        # 5. NAV
        cnav, tnav = cli.get("nav_before", 0), tuner.get("nav_before", 0)
        if abs(cnav - tnav) > max(cnav, tnav) * 0.0005:
            issues.append(f"  NAV: CLI={cnav:.2f} vs Tuner={tnav:.2f} (diff={tnav-cnav:+.2f})")

        if issues:
            if first_diff is None:
                first_diff = (i, date, issues)
                print(f"*** FIRST DIVERGENCE [{i}] {date} ***")
                for iss in issues:
                    print(iss)
                print()

            # Categorize
            for iss in issues:
                if iss.startswith("  SIGNAL"): categories["signal"] += 1
                elif ".px:" in iss: categories["px"] += 1
                elif iss.startswith("  HOLD"): categories["holding"] += 1
                elif iss.startswith("  CASH"): categories["cash"] += 1

    # Summary
    print(f"--- SUMMARY ---")
    print(f"Snapshots: {max_len}")
    print(f"Signal divergences:  {categories['signal']}")
    print(f"Price divergences:   {categories['px']}")
    print(f"Holding divergences: {categories['holding']}")
    print(f"Cash divergences:    {categories['cash']}")
    if first_diff:
        i, date, issues = first_diff
        print(f"\nRoot cause at [{i}] {date}:")
        for iss in issues:
            print(iss)

if __name__ == "__main__":
    main()
