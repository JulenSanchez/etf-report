"""Setup rules for etf-report skill.

Copies rule files from the skill's rules/ directory to the correct
location for the current AI environment:
  - CodeBuddy: .codebuddy/rules/*.mdc
  - Claude Code: .claude/rules/*.md

Usage:
  python scripts/setup_rules.py            # install all rules
  python scripts/setup_rules.py --dry-run  # preview without writing
  python scripts/setup_rules.py --list     # list available rules
"""
import os
import sys
import shutil

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_SRC = os.path.join(SKILL_DIR, "rules")

# Rule definitions: (filename_stem, scope, description)
# scope: "project" = goes to workspace .codebuddy/rules/ or .claude/rules/
#         "user" = goes to user-level ~/.codebuddy/rules/ or ~/.claude/rules/
RULES = [
    # Project-level rules (essential for etf-report)
    ("etf-report",            "project", "ETF report skill guard (release, version, bug)"),
    ("statusbar-protocol",    "project", "Status bar display protocol"),
]


def detect_ide():
    """Detect which IDE environment we're in."""
    # Check by looking at which config directory exists in the workspace
    workspace = os.path.dirname(os.path.dirname(SKILL_DIR))
    cb_dir = os.path.join(workspace, ".codebuddy")
    claude_dir = os.path.join(workspace, ".claude")

    results = []
    if os.path.isdir(cb_dir):
        results.append(("codebuddy", cb_dir))
    if os.path.isdir(claude_dir):
        results.append(("claude", claude_dir))

    if not results:
        # Default: check if running in CodeBuddy by environment
        results.append(("codebuddy", cb_dir))

    return results


def get_rules_dir(ide_name, scope, workspace_dir=None):
    """Get target directory for rules."""
    if ide_name == "codebuddy":
        ext = ".mdc"
        if scope == "project":
            base = os.path.join(workspace_dir, ".codebuddy", "rules") if workspace_dir else None
        else:
            base = os.path.join(os.path.expanduser("~"), ".codebuddy", "rules")
    else:  # claude
        ext = ".md"
        if scope == "project":
            base = os.path.join(workspace_dir, ".claude", "rules") if workspace_dir else None
        else:
            base = os.path.join(os.path.expanduser("~"), ".claude", "rules")
    return base, ext


def list_rules():
    """List all available rules."""
    print(f"Rules source: {RULES_SRC}\n")
    print(f"{'Name':<35} {'Scope':<10} {'Description'}")
    print("-" * 80)
    for stem, scope, desc in RULES:
        mdc = os.path.join(RULES_SRC, f"{stem}.mdc")
        md = os.path.join(RULES_SRC, f"{stem}.md")
        has_mdc = "Y" if os.path.exists(mdc) else "-"
        has_md = "Y" if os.path.exists(md) else "-"
        print(f"{stem:<35} {scope:<10} {desc}")
        print(f"  {'':35} .mdc=[{has_mdc}]  .md=[{has_md}]")


def install_rules(dry_run=False):
    """Install rules to the detected IDE environments."""
    workspace_dir = os.path.dirname(os.path.dirname(SKILL_DIR))
    ides = detect_ide()

    if not ides:
        print("ERROR: Could not detect IDE environment.")
        return False

    installed = 0
    skipped = 0

    for ide_name, _ in ides:
        print(f"\n{'[DRY RUN] ' if dry_run else ''}IDE: {ide_name}")
        print("=" * 50)

        for stem, scope, desc in RULES:
            target_dir, ext = get_rules_dir(ide_name, scope, workspace_dir)
            if not target_dir:
                print(f"  SKIP {stem}: cannot determine target directory")
                skipped += 1
                continue

            # Find source file (prefer matching extension, fallback to either)
            src_file = os.path.join(RULES_SRC, f"{stem}{ext}")
            if not os.path.exists(src_file):
                src_file = os.path.join(RULES_SRC, f"{stem}.mdc")
            if not os.path.exists(src_file):
                src_file = os.path.join(RULES_SRC, f"{stem}.md")
            if not os.path.exists(src_file):
                print(f"  SKIP {stem}: source file not found in {RULES_SRC}")
                skipped += 1
                continue

            target_file = os.path.join(target_dir, f"{stem}{ext}")
            scope_label = "workspace" if scope == "project" else "user"

            if os.path.exists(target_file):
                # Compare content
                with open(src_file, "r", encoding="utf-8") as f:
                    src_content = f.read()
                with open(target_file, "r", encoding="utf-8") as f:
                    tgt_content = f.read()
                if src_content == tgt_content:
                    print(f"  OK   {stem}{ext} ({scope_label}) — already up to date")
                    skipped += 1
                    continue
                else:
                    print(f"  {'WOULD UPDATE' if dry_run else 'UPDATE'} {stem}{ext} ({scope_label})")
            else:
                print(f"  {'WOULD INSTALL' if dry_run else 'INSTALL'} {stem}{ext} ({scope_label})")

            if not dry_run:
                os.makedirs(target_dir, exist_ok=True)
                shutil.copy2(src_file, target_file)
                installed += 1
            else:
                installed += 1

    print(f"\n{'Would install/update' if dry_run else 'Installed/updated'}: {installed}, skipped: {skipped}")
    return True


def main():
    if "--list" in sys.argv:
        list_rules()
    elif "--dry-run" in sys.argv:
        install_rules(dry_run=True)
    else:
        install_rules(dry_run=False)


if __name__ == "__main__":
    main()
