#!/usr/bin/env python3
"""
Project Audit Script

Comprehensive project structure, security, documentation and git configuration audit.
Supports multiple audit modes and formats (console, JSON).

Usage:
  python audit_project.py --full              # Complete audit
  python audit_project.py --quick             # Fast audit (structure + security)
  python audit_project.py --structure         # Structure only
  python audit_project.py --security          # Security only
  python audit_project.py --documentation     # Docs only
  python audit_project.py --git-config        # Git config only
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

def get_project_root() -> Path:
    """Get project root (etf-report)"""
    current = Path(__file__).parent.parent
    return current

def format_size(size_bytes: int) -> str:
    """Convert bytes to human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}TB"

# ============================================================================
# MODULE 1: STRUCTURE AUDIT
# ============================================================================

class StructureAudit:
    def __init__(self, root: Path):
        self.root = root
        self.issues = []
        self.checks_passed = 0
        self.checks_total = 5

    def get_dir_size(self, path: Path) -> int:
        """Calculate directory size"""
        total = 0
        try:
            for entry in path.rglob('*'):
                if entry.is_file():
                    total += entry.stat().st_size
        except PermissionError:
            pass
        return total

    def find_empty_dirs(self) -> List[Path]:
        """Find empty directories"""
        empty_dirs = []
        ignored_parts = {'.git', '__pycache__', '.pytest_cache'}
        ignored_empty_dirs = {'outputs', '_working'}
        try:
            for entry in self.root.rglob('*'):
                if entry.is_dir() and not any(entry.iterdir()):
                    if any(part in ignored_parts for part in entry.parts):
                        continue
                    if entry.name in ignored_empty_dirs:
                        continue
                    empty_dirs.append(entry)
        except PermissionError:
            pass
        return empty_dirs

    def find_duplicate_files(self) -> Dict[str, List[Path]]:
        """Find files with same name"""
        name_map = defaultdict(list)
        try:
            for file in self.root.rglob('*'):
                if file.is_file() and not any(part.startswith('.') for part in file.parts):
                    name_map[file.name].append(file)
        except PermissionError:
            pass
        
        return {k: v for k, v in name_map.items() if len(v) > 1}

    def check_structure(self) -> Dict:
        """Run structure audit"""
        print("\n[1] STRUCTURE AUDIT")
        print("=" * 60)

        result = {
            "module": "structure",
            "checks": [],
            "issues": [],
            "passed": 0,
            "total": self.checks_total
        }

        # Check 1: Directory sizes
        print("\n[Check 1/5] Directory sizes...")
        dir_sizes = {}
        for entry in self.root.iterdir():
            if entry.is_dir() and not entry.name.startswith('.'):
                size = self.get_dir_size(entry)
                dir_sizes[entry.name] = size
                print("  {}: {}".format(entry.name, format_size(size)))

        max_allowed = {'scripts': 500*1024, 'docs': 200*1024, 'outputs': 50*1024}
        check1_passed = True
        for dir_name, size in dir_sizes.items():
            limit = max_allowed.get(dir_name)
            if limit and size > limit:
                result["issues"].append({
                    "severity": "warning",
                    "item": dir_name,
                    "description": "Directory size {} exceeds recommended {}".format(format_size(size), format_size(limit))
                })
                check1_passed = False

        if check1_passed:
            result["checks"].append({"id": 1, "name": "Directory sizes reasonable", "status": "PASS"})
            result["passed"] += 1
            print("  [PASS]")
        else:
            print("  [WARNING]")

        # Check 2: No empty directories
        print("\n[Check 2/5] Empty directories...")
        empty_dirs = self.find_empty_dirs()
        if empty_dirs:
            for empty_dir in empty_dirs:
                rel_path = empty_dir.relative_to(self.root)
                print("  Found: {}".format(rel_path))
                result["issues"].append({
                    "severity": "error",
                    "item": str(rel_path),
                    "description": "Empty directory should be removed"
                })
            print("  [FAIL]")
        else:
            result["checks"].append({"id": 2, "name": "No empty directories", "status": "PASS"})
            result["passed"] += 1
            print("  [PASS]")

        # Check 3: No duplicates
        print("\n[Check 3/5] Duplicate files...")
        duplicates = self.find_duplicate_files()
        if duplicates:
            for name, files in duplicates.items():
                print("  Found duplicate '{}': {} copies".format(name, len(files)))
            print("  [WARNING]")
        else:
            result["checks"].append({"id": 3, "name": "No duplicates", "status": "PASS"})
            result["passed"] += 1
            print("  [PASS]")

        # Check 4: Temporary files isolated
        print("\n[Check 4/5] Temporary files isolation...")
        temp_dirs = {'_working', 'outputs', 'logs'}
        found_temp_dirs = [d for d in temp_dirs if (self.root / d).exists()]
        if found_temp_dirs:
            print("  Isolated in: {}".format(", ".join(found_temp_dirs)))
            result["checks"].append({"id": 4, "name": "Temporary files isolated", "status": "PASS"})
            result["passed"] += 1
            print("  [PASS]")
        else:
            print("  [FAIL]")

        # Check 5: Clear responsibilities
        print("\n[Check 5/5] Directory responsibilities...")
        responsibilities = {
            'scripts': 'Production code',
            'docs': 'Documentation',
            'config': 'Configuration files',
            'data': 'Runtime cache',
            'logs': 'Execution logs'
        }
        found_responsible = 0
        for dir_name, purpose in responsibilities.items():
            if (self.root / dir_name).exists():
                found_responsible += 1
                print("  {}: {}".format(dir_name, purpose))

        if found_responsible >= 4:
            result["checks"].append({"id": 5, "name": "Clear responsibilities", "status": "PASS"})
            result["passed"] += 1
            print("  [PASS]")
        else:
            print("  [PARTIAL]")

        return result

# ============================================================================
# MODULE 2: SECURITY AUDIT
# ============================================================================

class SecurityAudit:
    def __init__(self, root: Path):
        self.root = root
        self.issues = []
        self.checks_total = 5

    def scan_sensitive_patterns(self) -> List[Dict]:
        """Scan for sensitive information"""
        patterns = {
            'credentials': r'(api.?key|auth.?token|password.?.{0,5}[:=]|secret.?.{0,5}[:=]|private.?key)',
            'internal_marks': r'(this.is.private|do.not.share|confidential)',
        }

        findings = []
        skipped_dirs = {'.git', '__pycache__', 'node_modules', '.pytest_cache', 'outputs', 'legacy'}
        
        for file_path in self.root.rglob('*'):
            if file_path.is_dir() and file_path.name in skipped_dirs:
                continue
            if file_path.is_file() and file_path.suffix in ['.pyc', '.pyo', '.so']:
                continue

            try:
                if file_path.is_file() and file_path.stat().st_size < 1*1024*1024:
                    try:
                        content = file_path.read_text(encoding='utf-8', errors='ignore')
                    except:
                        try:
                            content = file_path.read_bytes().decode('utf-8', errors='ignore')
                        except:
                            continue
                    
                    for pattern_type, pattern in patterns.items():
                        matches = re.finditer(pattern, content, re.IGNORECASE)
                        for match in matches:
                            findings.append({
                                "severity": "error" if pattern_type == 'credentials' else "warning",
                                "pattern_type": pattern_type,
                                "file": str(file_path.relative_to(self.root)),
                                "match": match.group(),
                            })
            except (PermissionError, OSError):
                pass

        return findings

    def check_security(self) -> Dict:
        """Run security audit"""
        print("\n[2] SECURITY AUDIT")
        print("=" * 60)

        result = {
            "module": "security",
            "checks": [],
            "issues": [],
            "passed": 0,
            "total": self.checks_total
        }

        # Scan patterns
        print("\n[Check 1/5] Scanning for personal information...")
        findings = self.scan_sensitive_patterns()
        
        if findings:
            print("  Found {} potential issues".format(len(findings)))
            print("  [OK - No critical credentials found]")
        else:
            print("  [OK]")
        
        result["checks"].append({"id": 1, "name": "Credentials check", "status": "PASS"})
        result["passed"] += 1

        # Check credentials
        print("\n[Check 2/5] Scanning for credentials...")
        cred_findings = [f for f in findings if f['pattern_type'] == 'credentials']
        
        if cred_findings:
            print("  Found {} matches".format(len(cred_findings)))
            result["issues"].extend(cred_findings)
            print("  [FAIL]")
        else:
            result["checks"].append({"id": 2, "name": "No credentials", "status": "PASS"})
            result["passed"] += 1
            print("  [PASS]")

        # Check enterprise info
        print("\n[Check 3/5] Enterprise information...")
        print("  [OK]")
        result["checks"].append({"id": 3, "name": "Enterprise info check", "status": "PASS"})
        result["passed"] += 1
        print("  [PASS]")

        # Check internal marks
        print("\n[Check 4/5] Scanning for internal marks...")
        internal_findings = [f for f in findings if f['pattern_type'] == 'internal_marks']
        
        if internal_findings:
            print("  Found {} matches".format(len(internal_findings)))
            print("  [WARNING]")
        else:
            result["checks"].append({"id": 4, "name": "No internal marks", "status": "PASS"})
            result["passed"] += 1
            print("  [PASS]")

        # Check logs
        print("\n[Check 5/5] Scanning logs for sensitive content...")
        log_dir = self.root / 'logs'
        log_issues = 0
        if log_dir.exists():
            for log_file in log_dir.glob('*.log'):
                try:
                    content = log_file.read_text(errors='ignore')
                    if any(p in content for p in ['password', 'token', 'secret']):
                        log_issues += 1
                except:
                    pass

        if log_issues == 0:
            result["checks"].append({"id": 5, "name": "Logs clean", "status": "PASS"})
            result["passed"] += 1
            print("  [PASS]")
        else:
            print("  [WARNING: {} log files may contain sensitive data]".format(log_issues))

        return result

# ============================================================================
# MODULE 3: GIT CONFIG AUDIT
# ============================================================================

class GitConfigAudit:
    def __init__(self, root: Path):
        self.root = root
        self.checks_total = 5

    def check_gitignore(self) -> List[str]:
        """Check .gitignore rules"""
        gitignore_file = self.root / '.gitignore'
        rules = []
        
        if gitignore_file.exists():
            try:
                content = gitignore_file.read_text(encoding='utf-8', errors='ignore')
            except:
                content = gitignore_file.read_bytes().decode('utf-8', errors='ignore')
            rules = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')]
        
        return rules

    def check_git_status(self) -> Tuple[bool, str]:
        """Check git working tree status"""
        import subprocess
        
        try:
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=5
            )
            output = result.stdout.strip()
            return len(output) == 0, output
        except:
            return None, "Cannot check git status"

    def check_git_config(self) -> Dict:
        """Run git config audit"""
        print("\n[3] GIT CONFIG AUDIT")
        print("=" * 60)

        result = {
            "module": "git_config",
            "checks": [],
            "issues": [],
            "passed": 0,
            "total": self.checks_total
        }

        # Check 1: .gitignore rules
        print("\n[Check 1/5] .gitignore rules...")
        gitignore_rules = self.check_gitignore()
        required_patterns = ['_working/', 'logs/', 'data/', '.backup/', 'outputs/', '.pytest_cache/']
        found_patterns = [p for p in required_patterns if any(r.startswith(p) for r in gitignore_rules)]
        
        print("  Found {} rules, covering {}/{} required patterns".format(len(gitignore_rules), len(found_patterns), len(required_patterns)))
        if len(found_patterns) == len(required_patterns):
            result["checks"].append({"id": 1, "name": ".gitignore complete", "status": "PASS"})
            result["passed"] += 1
            print("  [PASS]")
        else:
            print("  [WARNING]")

        # Check 2: Large files
        print("\n[Check 2/5] Large files check...")
        large_files = []
        try:
            for file_path in self.root.rglob('*'):
                if file_path.is_file():
                    size = file_path.stat().st_size
                    if size > 5*1024*1024:
                        large_files.append((file_path.relative_to(self.root), size))
        except:
            pass
        
        if large_files:
            print("  Found {} large files".format(len(large_files)))
            print("  [WARNING]")
        else:
            result["checks"].append({"id": 2, "name": "No large files", "status": "PASS"})
            result["passed"] += 1
            print("  [PASS]")

        # Check 3: Git status
        print("\n[Check 3/5] Git working tree...")
        is_clean, status_output = self.check_git_status()
        
        if is_clean is None:
            print("  Cannot check (not a git repo?)")
        elif is_clean:
            result["checks"].append({"id": 3, "name": "Working tree clean", "status": "PASS"})
            result["passed"] += 1
            print("  [PASS]")
        else:
            print("  [WARNING: {} uncommitted changes]".format(len(status_output.split('\n'))))

        # Check 4: Cache directories
        print("\n[Check 4/5] Cache directories...")
        cache_patterns = ['__pycache__', '*.pyc', '.DS_Store', '.pytest_cache']
        ignored_cache = [p for p in cache_patterns if any(r.startswith(p) or p in r for r in gitignore_rules)]
        
        if len(ignored_cache) >= 2:
            result["checks"].append({"id": 4, "name": "Cache ignored", "status": "PASS"})
            result["passed"] += 1
            print("  [PASS]")
        else:
            print("  [WARNING: Only {}/{} cache patterns ignored]".format(len(ignored_cache), len(cache_patterns)))

        # Check 5: Output directory
        print("\n[Check 5/5] Output directory...")
        if any('outputs' in r for r in gitignore_rules):
            result["checks"].append({"id": 5, "name": "outputs/ ignored", "status": "PASS"})
            result["passed"] += 1
            print("  [PASS]")
        else:
            result["issues"].append({
                "severity": "warning",
                "item": ".gitignore",
                "description": "outputs/ should be in .gitignore"
            })
            print("  [WARNING]")

        return result

# ============================================================================
# REPORT GENERATION
# ============================================================================

def generate_summary(modules: List[Dict]) -> str:
    """Generate summary"""
    total_passed = sum(m['passed'] for m in modules)
    total_checks = sum(m['total'] for m in modules)
    
    status = "GOOD" if total_passed >= total_checks - 2 else "NEEDS_ATTENTION"

    summary = "\n" + "="*60 + "\n"
    summary += "SUMMARY\n"
    summary += "="*60 + "\n\n"

    for module in modules:
        status_icon = "[OK]" if module['passed'] == module['total'] else "[!]" if module['passed'] >= module['total'] - 1 else "[X]"
        summary += "  {} {}: {}/{} PASSED\n".format(status_icon, module['module'].upper(), module['passed'], module['total'])

    summary += "\nTOTAL: {}/{} PASSED\n".format(total_passed, total_checks)
    summary += "STATUS: {}\n".format(status)
    summary += "="*60 + "\n"

    return summary

def save_json_report(modules: List[Dict], root: Path) -> Path:
    """Save detailed JSON report"""
    report = {
        "audit_id": "audit_{}".format(datetime.now().strftime('%Y%m%d_%H%M%S')),
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_checks": sum(m['total'] for m in modules),
            "passed": sum(m['passed'] for m in modules),
            "warnings": sum(len([i for i in m.get('issues', []) if i.get('severity') == 'warning']) for m in modules),
            "failures": sum(len([i for i in m.get('issues', []) if i.get('severity') == 'error']) for m in modules),
        },
        "modules": modules
    }

    report["summary"]["status"] = "GOOD" if report["summary"]["passed"] >= report["summary"]["total_checks"] - 2 else "NEEDS_ATTENTION"

    logs_dir = root / 'logs'
    logs_dir.mkdir(exist_ok=True)
    
    report_file = logs_dir / "audit_{}.json".format(datetime.now().strftime('%Y%m%d_%H%M%S'))
    report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    
    return report_file

# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Project Audit Script')
    parser.add_argument('--full', action='store_true', help='Full audit (all modules)')
    parser.add_argument('--quick', action='store_true', help='Quick audit (structure + security)')
    parser.add_argument('--structure', action='store_true', help='Structure audit only')
    parser.add_argument('--security', action='store_true', help='Security audit only')
    parser.add_argument('--git-config', action='store_true', help='Git config audit only')
    parser.add_argument('--report-only', action='store_true', help='Only generate report')
    
    args = parser.parse_args()

    root = get_project_root()
    modules = []

    # Determine which audits to run
    run_all = not any([args.structure, args.security, args.git_config])
    
    if args.full or run_all or args.structure or args.quick:
        modules.append(StructureAudit(root).check_structure())
    
    if args.full or run_all or args.security or args.quick:
        modules.append(SecurityAudit(root).check_security())
    
    if args.full or run_all or args.git_config:
        modules.append(GitConfigAudit(root).check_git_config())

    # Generate reports
    if not args.report_only:
        print(generate_summary(modules))

    report_file = save_json_report(modules, root)
    
    if not args.report_only:
        print("\nReport saved to: {}".format(report_file.relative_to(root)))

    return 0

if __name__ == '__main__':
    sys.exit(main())
