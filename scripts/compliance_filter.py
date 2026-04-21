#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REQ-158 Step B：公开内容合规过滤器

设计原则：偏宽 > 偏严，block 最少，所有 block 必审计。
接入点：scripts/editorial_fetcher.py 抓回原始条目后，调用 filter_batch() 过滤。

公开 API：
    filter_one(item, rules) -> FilterResult
        item 字段约定：{"title": str, "url": str, "date": str, "source": str}
        FilterResult: namedtuple(decision, reasons, transformed_item)
          decision ∈ {"pass", "flag", "block"}
          reasons:  list of {"rule_type", "category/description", "matched"}
          transformed_item: 若 flag，item 会在 title 前加 "[弱相关] "

    filter_batch(items, rules) -> (kept, blocked, stats)
        kept:    全部 pass 与 flag 的 item（flag 已改写 title）
        blocked: 全部 block 的 item + 命中原因
        stats:   {"total", "passed", "flagged", "blocked", "block_rate"}

    write_audit(blocked, kept_flagged, stats, date=None)
        向 logs/compliance_audit_YYYYMMDD.jsonl 追加审计
        同时重写 logs/compliance_daily_summary_YYYYMMDD.md 日度摘要

所有 block 的阈值超标会在 stdout 输出 WARN（供 update_report.py 感知）。
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import yaml


SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RULES_PATH = os.path.join(SKILL_DIR, "config", "compliance_rules.yaml")
DEFAULT_LOG_DIR = os.path.join(SKILL_DIR, "logs")


# ------------------------------------------------------------
# 数据结构
# ------------------------------------------------------------
@dataclass
class FilterResult:
    decision: str  # "pass" | "flag" | "block"
    reasons: List[Dict] = field(default_factory=list)
    transformed_item: Optional[Dict] = None


@dataclass
class BatchStats:
    total: int = 0
    passed: int = 0
    flagged: int = 0
    blocked: int = 0

    @property
    def block_rate(self) -> float:
        return (self.blocked / self.total) if self.total else 0.0

    def to_dict(self) -> Dict:
        return {
            "total": self.total,
            "passed": self.passed,
            "flagged": self.flagged,
            "blocked": self.blocked,
            "block_rate": round(self.block_rate, 4),
        }


# ------------------------------------------------------------
# 规则加载
# ------------------------------------------------------------
def load_rules(rules_path: str = DEFAULT_RULES_PATH) -> Dict:
    """加载 compliance_rules.yaml，并预编译正则。"""
    with open(rules_path, "r", encoding="utf-8") as f:
        rules = yaml.safe_load(f) or {}

    # 预编译正则（提升批量过滤性能）
    for rl in rules.get("investment_red_lines", []) or []:
        rl["_compiled"] = re.compile(rl["pattern"])
    for np in rules.get("noise_patterns", []) or []:
        np["_compiled"] = re.compile(np["pattern"])

    return rules


# ------------------------------------------------------------
# 单条过滤
# ------------------------------------------------------------
def filter_one(item: Dict, rules: Dict) -> FilterResult:
    """对单条资讯做三级过滤：sensitive → red_lines → noise。"""
    title = (item.get("title") or "").strip()
    if not title:
        # 空标题视为噪音，直接 block（不算合规问题，算数据问题）
        return FilterResult(
            decision="block",
            reasons=[{"rule_type": "data_integrity", "description": "标题为空", "matched": ""}],
        )

    text = title  # 目前只拿到 title；未来扩展可含 summary

    # 1. 敏感词（block）
    for group in rules.get("sensitive_keywords", []) or []:
        category = group.get("category", "unknown")
        for kw in group.get("keywords", []) or []:
            if kw in text:
                return FilterResult(
                    decision="block",
                    reasons=[{
                        "rule_type": "sensitive_keyword",
                        "category": category,
                        "matched": kw,
                    }],
                )

    # 2. 投资合规红线（block）
    for rl in rules.get("investment_red_lines", []) or []:
        compiled = rl.get("_compiled") or re.compile(rl["pattern"])
        m = compiled.search(text)
        if m:
            return FilterResult(
                decision="block",
                reasons=[{
                    "rule_type": "investment_red_line",
                    "description": rl.get("description", ""),
                    "pattern": rl.get("pattern"),
                    "matched": m.group(0),
                }],
            )

    # 3. 噪音模式（flag，加 [弱相关] 前缀）
    noise_hits = []
    for np in rules.get("noise_patterns", []) or []:
        compiled = np.get("_compiled") or re.compile(np["pattern"])
        m = compiled.search(text)
        if m:
            noise_hits.append({
                "rule_type": "noise_pattern",
                "description": np.get("description", ""),
                "pattern": np.get("pattern"),
                "matched": m.group(0),
            })
    if noise_hits:
        new_item = dict(item)
        new_item["title"] = "[弱相关] " + title
        return FilterResult(
            decision="flag",
            reasons=noise_hits,
            transformed_item=new_item,
        )

    # 4. 通过
    return FilterResult(decision="pass", transformed_item=item)


# ------------------------------------------------------------
# 批量过滤
# ------------------------------------------------------------
def filter_batch(
    items: List[Dict],
    rules: Optional[Dict] = None,
) -> Tuple[List[Dict], List[Dict], BatchStats]:
    """对批量 items 过滤。返回 (保留的, 被拦截的带原因, 统计)."""
    if rules is None:
        rules = load_rules()

    kept: List[Dict] = []
    blocked: List[Dict] = []
    stats = BatchStats(total=len(items))

    for item in items:
        result = filter_one(item, rules)
        if result.decision == "block":
            stats.blocked += 1
            blocked.append({
                "item": item,
                "reasons": result.reasons,
                "filtered_at": datetime.now().isoformat(timespec="seconds"),
            })
        elif result.decision == "flag":
            stats.flagged += 1
            kept.append(result.transformed_item or item)
        else:
            stats.passed += 1
            kept.append(result.transformed_item or item)

    return kept, blocked, stats


# ------------------------------------------------------------
# 审计日志与日度摘要
# ------------------------------------------------------------
def write_audit(
    blocked: List[Dict],
    kept: List[Dict],
    stats: BatchStats,
    *,
    run_context: Optional[Dict] = None,
    date: Optional[str] = None,
    log_dir: str = DEFAULT_LOG_DIR,
    rules: Optional[Dict] = None,
) -> Tuple[str, str]:
    """
    写入两个文件：
      1. logs/compliance_audit_YYYYMMDD.jsonl  — 逐条 block 明细（append-only）
      2. logs/compliance_daily_summary_YYYYMMDD.md — 日度汇总（每次覆写）

    返回 (audit_path, summary_path)。
    """
    if rules is None:
        rules = load_rules()

    today = date or datetime.now().strftime("%Y%m%d")
    os.makedirs(log_dir, exist_ok=True)

    audit_tpl = (rules.get("runtime") or {}).get(
        "audit_log_path", "logs/compliance_audit_{date}.jsonl"
    )
    summary_tpl = (rules.get("runtime") or {}).get(
        "daily_summary_path", "logs/compliance_daily_summary_{date}.md"
    )

    audit_path = os.path.join(
        SKILL_DIR, audit_tpl.format(date=today)
    )
    summary_path = os.path.join(
        SKILL_DIR, summary_tpl.format(date=today)
    )
    os.makedirs(os.path.dirname(audit_path), exist_ok=True)

    # 1. 逐条 append
    with open(audit_path, "a", encoding="utf-8") as f:
        for entry in blocked:
            record = {
                "audit_ts": datetime.now().isoformat(timespec="seconds"),
                "run_context": run_context or {},
                "blocked": entry,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 2. 覆写日度摘要
    _write_daily_summary(summary_path, blocked, kept, stats, rules, today, run_context)

    # 3. 拦截率告警
    threshold = (rules.get("runtime") or {}).get("block_rate_warn_threshold", 0.10)
    if stats.total > 0 and stats.block_rate > threshold:
        print(
            f"[compliance_filter] WARN: 拦截率 {stats.block_rate:.1%} "
            f"超过阈值 {threshold:.0%}（{stats.blocked}/{stats.total}）。"
            f"详情见 {summary_path}",
            file=sys.stderr,
        )

    return audit_path, summary_path


def _write_daily_summary(
    path: str,
    blocked: List[Dict],
    kept: List[Dict],
    stats: BatchStats,
    rules: Dict,
    date: str,
    run_context: Optional[Dict] = None,
) -> None:
    """生成人类可读的日度摘要 markdown。"""
    flagged_kept = [k for k in kept if isinstance(k.get("title"), str) and k["title"].startswith("[弱相关]")]

    # 统计最常命中的规则
    rule_counter: Counter = Counter()
    for entry in blocked:
        for r in entry.get("reasons", []):
            key = (
                r.get("category")
                or r.get("description")
                or r.get("rule_type", "unknown")
            )
            rule_counter[key] += 1

    lines = []
    lines.append(f"# 合规过滤日度摘要 — {date}")
    lines.append("")
    if run_context:
        lines.append(f"> 运行上下文：`{json.dumps(run_context, ensure_ascii=False)}`")
        lines.append("")
    lines.append("## 总览")
    lines.append("")
    lines.append(f"- 抓取条目总数：**{stats.total}**")
    lines.append(f"- 通过（pass）：{stats.passed}")
    lines.append(f"- 标记（flag 弱相关）：{stats.flagged}")
    lines.append(f"- 拦截（block）：**{stats.blocked}**（占比 {stats.block_rate:.1%}）")
    threshold = (rules.get("runtime") or {}).get("block_rate_warn_threshold", 0.10)
    if stats.block_rate > threshold:
        lines.append("")
        lines.append(f"> ⚠️ **拦截率超过阈值 {threshold:.0%}，建议检查规则是否过严或上游数据异常。**")
    lines.append("")

    if rule_counter:
        lines.append("## 命中规则 Top 5")
        lines.append("")
        for rule_key, count in rule_counter.most_common(5):
            lines.append(f"- `{rule_key}` — {count} 次")
        lines.append("")

    if blocked:
        lines.append("## 被拦截条目明细")
        lines.append("")
        for i, entry in enumerate(blocked, 1):
            item = entry.get("item", {})
            title = item.get("title", "(无标题)")
            url = item.get("url", "")
            source = item.get("source", "")
            reasons = entry.get("reasons", [])
            reason_strs = []
            for r in reasons:
                rt = r.get("rule_type", "?")
                matched = r.get("matched", "")
                desc = r.get("category") or r.get("description", "")
                reason_strs.append(f"[{rt}] {desc} (命中: `{matched}`)")
            lines.append(f"### {i}. {title[:80]}")
            lines.append("")
            lines.append(f"- 来源：{source}")
            if url:
                lines.append(f"- 链接：<{url}>")
            lines.append(f"- 命中原因：{'; '.join(reason_strs)}")
            lines.append("")

    if flagged_kept:
        lines.append(f"## 标记为 [弱相关] 但保留的条目（{len(flagged_kept)}）")
        lines.append("")
        for item in flagged_kept[:20]:  # 最多展示 20 条
            lines.append(f"- {item.get('title', '')[:100]}")
        lines.append("")

    lines.append("")
    lines.append("---")
    lines.append(f"*生成于 {datetime.now().isoformat(timespec='seconds')} — REQ-158 合规过滤器*")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ------------------------------------------------------------
# CLI（便于手动调试）
# ------------------------------------------------------------
def main():
    """独立运行：从 stdin 读 JSON list，过滤后输出到 stdout。
    用于调试：cat items.json | python compliance_filter.py
    """
    import argparse
    parser = argparse.ArgumentParser(description="公开内容合规过滤器")
    parser.add_argument("--input", "-i", help="输入 JSON 文件（list of items）")
    parser.add_argument("--rules", "-r", default=DEFAULT_RULES_PATH, help="规则文件路径")
    parser.add_argument("--no-audit", action="store_true", help="不写审计日志")
    args = parser.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            items = json.load(f)
    else:
        items = json.load(sys.stdin)

    rules = load_rules(args.rules)
    kept, blocked, stats = filter_batch(items, rules)

    print(json.dumps({
        "stats": stats.to_dict(),
        "kept_count": len(kept),
        "blocked_count": len(blocked),
    }, ensure_ascii=False, indent=2))

    if not args.no_audit:
        audit_path, summary_path = write_audit(
            blocked, kept, stats,
            run_context={"trigger": "cli"},
            rules=rules,
        )
        print(f"审计日志: {audit_path}", file=sys.stderr)
        print(f"日度摘要: {summary_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
