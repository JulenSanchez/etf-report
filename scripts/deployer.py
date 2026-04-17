#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Pages 部署

Step 8 of --publish mode:
1. 将技能根目录的 index.html 复制到 GitHub Pages 仓库
2. 在 GitHub Pages 仓库中 git add/commit/push

架构说明：
- 技能源码仓库: Claw/.codebuddy/skills/etf-report/ (push 源码改动)
- Pages 部署仓库: github-pages/etf-report/ (push index.html 供 Pages 展示)
"""

import os
import shutil
import subprocess
from datetime import datetime
from typing import List

from logger import Logger
from config_manager import get_config

logger = Logger(name="deployer", level="INFO", file_output=True)


def _run_git(repo_root: str, args: List[str]) -> subprocess.CompletedProcess:
    """执行 git 命令并返回结果"""
    cmd = ["git", "-C", repo_root] + args
    logger.info("执行 git 命令", {"command": " ".join(cmd)})
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def _deploy_to_source_repo(config: dict) -> bool:
    """部署到技能源码仓库（提交 index.html + data 文件）

    Args:
        config: publish.github 配置段
    """
    repo_root = config.get("repo_root", "")
    branch = config.get("branch", "main")
    commit_files = config.get("commit_files", [])
    commit_msg_template = config.get("commit_message", "data: ETF daily report update - {date}")

    if not repo_root or not os.path.isdir(repo_root):
        logger.warn("源码仓库 repo_root 无效，跳过", {"path": repo_root})
        return True

    # 验证 git 仓库
    result = _run_git(repo_root, ["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        logger.warn("不是有效的 git 仓库，跳过源码提交", {"path": repo_root})
        return True

    logger.info("部署到源码仓库", {"path": repo_root})

    # 检查当前分支
    result = _run_git(repo_root, ["branch", "--show-current"])
    current_branch = result.stdout.strip()
    if current_branch != branch:
        logger.info("切换到目标分支", {"from": current_branch, "to": branch})
        _run_git(repo_root, ["checkout", branch])

    # Git add 指定文件
    for filepath in commit_files:
        abs_path = os.path.join(repo_root, filepath)
        if not os.path.exists(abs_path):
            logger.warn("文件不存在，跳过", {"file": filepath})
            continue
        result = _run_git(repo_root, ["add", filepath])
        if result.returncode != 0:
            logger.warn("git add 失败", {"file": filepath})
            continue

    # 检查是否有变更
    result = _run_git(repo_root, ["status", "--porcelain"])
    if not result.stdout.strip():
        logger.info("源码仓库无变更需要提交")
        return True

    # Commit + Push
    today = datetime.now().strftime("%Y-%m-%d")
    commit_msg = commit_msg_template.replace("{date}", today)
    result = _run_git(repo_root, ["commit", "-m", commit_msg])
    if result.returncode != 0:
        logger.error("源码仓库 git commit 失败", {"stderr": result.stderr.strip()})
        return False

    result = _run_git(repo_root, ["push", "--force", "--no-verify", "origin", branch])
    if result.returncode != 0:
        logger.error("源码仓库 git push 失败", {"stderr": result.stderr.strip()})
        return False

    logger.info("源码仓库推送成功", {"branch": branch})
    return True


def _deploy_to_pages_repo(config: dict, skill_dir: str, html_source_path: str = None) -> bool:
    """部署到 GitHub Pages 仓库（复制 index.html 并 push）

    Args:
        config: publish.github 配置段
        skill_dir: 技能根目录（index.html 所在位置）
    """
    pages_root = config.get("pages_repo_root", "")
    pages_branch = config.get("pages_branch", "main")

    if not pages_root or not os.path.isdir(pages_root):
        logger.warn("Pages 仓库路径无效，跳过 Pages 部署", {"path": pages_root})
        return True

    # 验证 git 仓库
    result = _run_git(pages_root, ["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        logger.warn("Pages 路径不是有效的 git 仓库，跳过", {"path": pages_root})
        return True

    logger.info("部署到 GitHub Pages 仓库", {"path": pages_root})

    # 复制 index.html
    src_html = html_source_path or os.path.join(skill_dir, "index.html")
    dst_html = os.path.join(pages_root, "index.html")


    if not os.path.exists(src_html):
        logger.error("源 index.html 不存在", {"path": src_html})
        return False

    shutil.copy2(src_html, dst_html)
    logger.info("index.html 已复制到 Pages 仓库", {
        "src": src_html,
        "dst": dst_html,
        "size_kb": os.path.getsize(dst_html) / 1024
    })

    # 检查当前分支
    result = _run_git(pages_root, ["branch", "--show-current"])
    current_branch = result.stdout.strip()
    if current_branch != pages_branch:
        _run_git(pages_root, ["checkout", pages_branch])

    # Git add
    _run_git(pages_root, ["add", "index.html"])

    # 检查是否有变更
    result = _run_git(pages_root, ["status", "--porcelain"])
    if not result.stdout.strip():
        logger.info("Pages 仓库无变更需要提交")
        return True

    # Commit + Push
    now_str = datetime.now().strftime("%Y-%m-%d-%H%M")
    commit_msg = f"Update-ETF-report-{now_str}"
    result = _run_git(pages_root, ["commit", "-m", commit_msg])
    if result.returncode != 0:
        logger.error("Pages 仓库 git commit 失败", {"stderr": result.stderr.strip()})
        return False

    result = _run_git(pages_root, ["push", "--force", "--no-verify", "origin", pages_branch])
    if result.returncode != 0:
        logger.error("Pages 仓库 git push 失败", {"stderr": result.stderr.strip()})
        return False

    logger.info("GitHub Pages 部署成功", {"branch": pages_branch})
    return True


def main(skill_dir: str, html_source_path: str = None) -> bool:
    """执行 GitHub 部署

    Args:
        skill_dir: 技能根目录的绝对路径
        html_source_path: 可选的发布 HTML 来源路径；为空时回退到技能根目录 index.html

    Returns:
        True 表示成功，False 表示失败
    """

    logger.info("=" * 60)
    logger.info("Step 8: 部署到 GitHub")
    logger.info("=" * 60)

    config = get_config()
    publish_config = config._config.get("publish", {})
    github_config = publish_config.get("github", {})

    if not github_config.get("enabled", False):
        logger.info("GitHub 部署未启用，跳过")
        return True

    # 8a: 提交到源码仓库（Claw/.codebuddy/skills/etf-report）
    ok1 = _deploy_to_source_repo(github_config)

    # 8b: 复制到 Pages 仓库并推送（github-pages/etf-report）
    ok2 = _deploy_to_pages_repo(github_config, skill_dir, html_source_path=html_source_path)


    if ok1 and ok2:
        logger.info("GitHub 部署全部完成")
        return True
    else:
        logger.error("GitHub 部署部分失败", {"source_repo": ok1, "pages_repo": ok2})
        return False


if __name__ == "__main__":
    import sys
    SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    success = main(SKILL_DIR)
    sys.exit(0 if success else 1)
