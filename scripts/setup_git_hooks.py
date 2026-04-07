#!/usr/bin/env python3
"""
设置 Git Hooks 用于安全检查

使用方式：
    python scripts/setup_git_hooks.py

该脚本会：
1. 在 .git/hooks/ 中创建 pre-commit hook
2. 在 .git/hooks/ 中创建 pre-push hook
3. 设置正确的执行权限
4. 验证 hook 配置
"""

import os
import sys
import stat
import subprocess
from pathlib import Path

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
GIT_HOOKS_DIR = PROJECT_ROOT / ".git" / "hooks"

# 检查 .git 目录是否存在
if not (PROJECT_ROOT / ".git").exists():
    print("ERROR: .git directory not found!")
    print(f"Please ensure you're in a Git repository: {PROJECT_ROOT}")
    sys.exit(1)

# 创建 hooks 目录（如果不存在）
GIT_HOOKS_DIR.mkdir(parents=True, exist_ok=True)

print("[*] Setting up Git Hooks...")
print(f"[*] Project root: {PROJECT_ROOT}")
print(f"[*] Hooks directory: {GIT_HOOKS_DIR}")

# ============================================================================
# Pre-commit Hook
# ============================================================================

PRE_COMMIT_HOOK = GIT_HOOKS_DIR / "pre-commit"
PRE_COMMIT_CONTENT = """#!/usr/bin/env python3
import os
import sys
import re
from pathlib import Path

def check_secrets():
    \"\"\"Check for potential secrets in staged files.\"\"\"
    print("[Pre-commit] Checking for secrets...")
    
    patterns = [
        r'password\\s*=',
        r'api_key\\s*=',
        r'secret_key\\s*=',
        r'token\\s*=',
        r'Authorization:\\s*Bearer',
        r'Authorization:\\s*Token',
    ]
    
    result = os.popen('git diff --cached --name-only').read()
    files = result.strip().split('\\n')
    
    found_secrets = False
    for file in files:
        if not file or file.startswith('.'):
            continue
        if not os.path.exists(file):
            continue
            
        try:
            with open(file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                for pattern in patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        print(f"  [!] WARNING: Potential secret in {file}")
                        found_secrets = True
        except:
            pass
    
    if found_secrets:
        print("[!] Found potential secrets. Aborting commit.")
        print("[*] If this is intentional, use: git commit --no-verify")
        return False
    return True

def check_syntax():
    \"\"\"Check Python syntax for modified .py files.\"\"\"
    print("[Pre-commit] Checking Python syntax...")
    
    result = os.popen('git diff --cached --name-only').read()
    py_files = [f for f in result.strip().split('\\n') if f.endswith('.py')]
    
    for file in py_files:
        if not os.path.exists(file):
            continue
        
        compile_result = os.system(f'python -m py_compile \"{file}\" 2>/dev/null')
        if compile_result != 0:
            print(f"  [!] Syntax error in {file}")
            return False
    
    return True

def check_file_sizes():
    \"\"\"Check for large files (> 50MB).\"\"\"
    print("[Pre-commit] Checking file sizes...")
    
    result = os.popen('git diff --cached --name-only').read()
    files = result.strip().split('\\n')
    
    MAX_SIZE = 50 * 1024 * 1024  # 50 MB
    
    for file in files:
        if not file or not os.path.exists(file):
            continue
        
        size = os.path.getsize(file)
        if size > MAX_SIZE:
            size_mb = size / (1024 * 1024)
            print(f"  [!] File too large: {file} ({size_mb:.1f} MB)")
            return False
    
    return True

def main():
    print("[Pre-commit Check] Running safety checks...")
    
    checks = [
        ("Secrets", check_secrets),
        ("Python Syntax", check_syntax),
        ("File Sizes", check_file_sizes),
    ]
    
    for name, check_func in checks:
        try:
            if not check_func():
                print(f"[!] {name} check failed!")
                return 1
        except Exception as e:
            print(f"[!] {name} check error: {e}")
            return 1
    
    print("[OK] All pre-commit checks passed!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
"""

PRE_COMMIT_HOOK.write_text(PRE_COMMIT_CONTENT)
os.chmod(PRE_COMMIT_HOOK, os.stat(PRE_COMMIT_HOOK).st_mode | stat.S_IEXEC | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
print(f"[OK] Created pre-commit hook: {PRE_COMMIT_HOOK}")

# ============================================================================
# Pre-push Hook
# ============================================================================

PRE_PUSH_HOOK = GIT_HOOKS_DIR / "pre-push"
PRE_PUSH_CONTENT = """#!/usr/bin/env python3
import os
import sys
import subprocess

def get_current_branch():
    \"\"\"Get current branch name.\"\"\"
    result = os.popen('git rev-parse --abbrev-ref HEAD').read().strip()
    return result

def get_commits_to_push():
    \"\"\"Get list of commits to be pushed.\"\"\"
    result = os.popen('git rev-list --count origin/master..HEAD').read().strip()
    try:
        return int(result)
    except:
        return 0

def confirm_push(message):
    \"\"\"Ask user for confirmation.\"\"\"
    print(f"\\n[WARNING] {message}")
    response = input("Continue? (yes/no): ").lower().strip()
    return response in ['yes', 'y']

def main():
    print("[Pre-push Check] Running safety checks...")
    
    branch = get_current_branch()
    protected = ['master', 'main']
    
    # Check if pushing to protected branch
    if branch in protected:
        print(f"[!] You are pushing to protected branch: {branch}")
        if not confirm_push(f"Direct push to '{branch}' is not recommended. Use PR instead."):
            print("[ABORT] Push cancelled by user.")
            return 1
    
    # Check commit count
    commits = get_commits_to_push()
    if commits > 5:
        print(f"[!] You are pushing {commits} commits")
        if not confirm_push(f"Large number of commits ({commits}). Proceed?"):
            print("[ABORT] Push cancelled by user.")
            return 1
    
    # Check for uncommitted changes
    status = os.popen('git status --porcelain').read().strip()
    if status:
        print("[!] Warning: You have uncommitted changes")
        if not confirm_push("Push with uncommitted changes?"):
            print("[ABORT] Push cancelled by user.")
            return 1
    
    print("[OK] Pre-push checks passed!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
"""

PRE_PUSH_HOOK.write_text(PRE_PUSH_CONTENT)
os.chmod(PRE_PUSH_HOOK, os.stat(PRE_PUSH_HOOK).st_mode | stat.S_IEXEC | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
print(f"[OK] Created pre-push hook: {PRE_PUSH_HOOK}")

# ============================================================================
# Verify
# ============================================================================

print("\n[*] Verifying hooks installation...")

for hook_file in [PRE_COMMIT_HOOK, PRE_PUSH_HOOK]:
    if hook_file.exists():
        mode = os.stat(hook_file).st_mode
        is_executable = bool(mode & stat.S_IXUSR)
        status = "executable" if is_executable else "NOT executable"
        print(f"  [OK] {hook_file.name}: {status}")
    else:
        print(f"  [ERROR] {hook_file.name}: not found")

print("\n[SUCCESS] Git Hooks setup complete!")
print("\nNow when you:")
print("  - commit: pre-commit checks will run (secrets, syntax, file sizes)")
print("  - push: pre-push checks will ask for confirmation on protected branches")
print("\nTo skip hooks (emergency only): git commit --no-verify")
