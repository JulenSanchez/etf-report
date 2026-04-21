# -*- coding: utf-8 -*-
"""
REQ-158 Step B 单测：compliance_filter 的三档判定 + 审计日志生成。
"""
import json
import os
import re
from datetime import datetime


def test_pass_normal_etf_news(load_module):
    """正常的 ETF 相关新闻应全部 pass。"""
    module = load_module("compliance_filter")
    rules = module.load_rules()

    items = [
        {"title": "宁德时代转身开矿", "url": "https://finance.sina.com.cn/r/1", "source": "sina_stock:sz300750"},
        {"title": "宁德时代2026年锂电确定性主线，华西证券维持买入评级", "url": "u", "source": "sina"},
        {"title": "百济神州2025年首次实现年度盈利", "url": "u", "source": "sina"},
        {"title": "英伟达与光通信企业签署战略合作", "url": "u", "source": "sina"},
        {"title": "港股创新药ETF估值处于历史低位", "url": "u", "source": "sina"},
    ]
    kept, blocked, stats = module.filter_batch(items, rules)

    assert stats.total == 5
    assert stats.passed == 5
    assert stats.blocked == 0
    assert stats.flagged == 0
    assert len(kept) == 5
    assert all(not item["title"].startswith("[弱相关]") for item in kept)


def test_block_sensitive_keywords(load_module):
    """命中涉政/涉暴/涉赌词应 block。"""
    module = load_module("compliance_filter")
    rules = module.load_rules()

    items = [
        {"title": "某境外敌对势力干预中国资本市场言论", "url": "u", "source": "s"},
        {"title": "台独分子再发挑衅言论", "url": "u", "source": "s"},
        {"title": "某机构疑似涉及恐怖组织资金流动", "url": "u", "source": "s"},
    ]
    kept, blocked, stats = module.filter_batch(items, rules)

    assert stats.blocked == 3
    assert stats.passed == 0
    assert len(blocked) == 3
    # 每条都有 sensitive_keyword 类型的 reason
    for entry in blocked:
        assert any(r["rule_type"] == "sensitive_keyword" for r in entry["reasons"])


def test_block_investment_red_lines(load_module):
    """命中违规推介话术应 block。"""
    module = load_module("compliance_filter")
    rules = module.load_rules()

    items = [
        {"title": "本基金保证收益10%，稳赚不赔", "url": "u", "source": "s"},
        {"title": "内部消息买入某科技股，明日必涨停", "url": "u", "source": "s"},
        {"title": "跟着庄家操纵节奏，3 天翻倍", "url": "u", "source": "s"},
        {"title": "代客理财专业团队，资金盘快速回报", "url": "u", "source": "s"},
    ]
    kept, blocked, stats = module.filter_batch(items, rules)

    assert stats.blocked == 4
    for entry in blocked:
        assert any(r["rule_type"] == "investment_red_line" for r in entry["reasons"])


def test_flag_noise_patterns_kept_with_prefix(load_module):
    """命中噪音模式应被保留但打 [弱相关] 前缀。"""
    module = load_module("compliance_filter")
    rules = module.load_rules()

    items = [
        {"title": "北京车展前瞻：181台首发新车大赏", "url": "u", "source": "s"},
        {"title": "开户送100元京东卡，限时福利", "url": "u", "source": "s"},
        {"title": "扫码加群领取内部股票池", "url": "u", "source": "s"},
    ]
    kept, blocked, stats = module.filter_batch(items, rules)

    # 这三条可能同时命中多个规则（扫码加群 和 "内部" 荐股）——
    # 扫码加群应该是 flag，而 "内部单" 这种投资红线是 block
    # 但本测试只关心车展 + 开户送钱这两类纯噪音
    assert len(kept) >= 2  # 至少车展和开户两条被 flag 保留
    flagged_items = [k for k in kept if k["title"].startswith("[弱相关]")]
    assert any("车展" in it["title"] for it in flagged_items)
    assert any("开户" in it["title"] or "送" in it["title"] for it in flagged_items)


def test_empty_title_blocked_as_data_integrity(load_module):
    """空标题视为数据完整性问题，block。"""
    module = load_module("compliance_filter")
    rules = module.load_rules()

    items = [{"title": "", "url": "u", "source": "s"},
             {"title": "   ", "url": "u", "source": "s"}]
    kept, blocked, stats = module.filter_batch(items, rules)
    assert stats.blocked == 2
    for entry in blocked:
        assert any(r["rule_type"] == "data_integrity" for r in entry["reasons"])


def test_mixed_batch_preserves_order_and_counts(load_module):
    """混合批量的计数准确 + 保留顺序。"""
    module = load_module("compliance_filter")
    rules = module.load_rules()

    items = [
        {"title": "宁德时代开矿布局上游", "url": "u", "source": "s"},          # pass
        {"title": "保证收益20%的神奇产品", "url": "u", "source": "s"},         # block (red_line)
        {"title": "北京车展首发新车21辆", "url": "u", "source": "s"},          # flag (noise)
        {"title": "百济神州GAAP净利润2.87亿美元", "url": "u", "source": "s"},  # pass
        {"title": "台独分子大放厥词", "url": "u", "source": "s"},              # block (sensitive)
    ]
    kept, blocked, stats = module.filter_batch(items, rules)
    assert stats.total == 5
    assert stats.passed == 2
    assert stats.flagged == 1
    assert stats.blocked == 2
    # kept 应该是 3 条（2 pass + 1 flag），按原顺序
    assert len(kept) == 3
    assert "宁德时代" in kept[0]["title"]
    assert kept[1]["title"].startswith("[弱相关]") and "车展" in kept[1]["title"]
    assert "百济神州" in kept[2]["title"]


def test_write_audit_creates_two_files(tmp_path, monkeypatch, load_module):
    """审计写入应生成 jsonl + md 两个文件。"""
    module = load_module("compliance_filter")

    # 让 log 写到 tmp_path
    monkeypatch.setattr(module, "DEFAULT_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(module, "SKILL_DIR", str(tmp_path))

    rules = module.load_rules()
    # 手动修一下 runtime 的 template 路径让它相对 tmp_path
    rules.setdefault("runtime", {})
    rules["runtime"]["audit_log_path"] = "compliance_audit_{date}.jsonl"
    rules["runtime"]["daily_summary_path"] = "compliance_daily_summary_{date}.md"

    items = [
        {"title": "宁德时代2026年一季报靓丽", "url": "u1", "source": "s"},     # pass
        {"title": "保证稳赚不赔的理财神器", "url": "u2", "source": "s"},       # block
        {"title": "北京车展前瞻新车大赏", "url": "u3", "source": "s"},         # flag
    ]
    kept, blocked, stats = module.filter_batch(items, rules)

    today = datetime.now().strftime("%Y%m%d")
    audit_path, summary_path = module.write_audit(
        blocked, kept, stats,
        run_context={"trigger": "unit_test"},
        date=today,
        log_dir=str(tmp_path),
        rules=rules,
    )

    assert os.path.exists(audit_path), f"audit file not created at {audit_path}"
    assert os.path.exists(summary_path), f"summary file not created at {summary_path}"

    # 检查 jsonl 每行是合法 JSON，且命中 block 记录
    with open(audit_path, "r", encoding="utf-8") as f:
        audit_lines = [json.loads(line) for line in f if line.strip()]
    assert len(audit_lines) == 1  # 只有 1 条 block
    assert audit_lines[0]["run_context"]["trigger"] == "unit_test"
    assert "保证" in audit_lines[0]["blocked"]["item"]["title"]

    # 检查 md 摘要包含关键字段
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = f.read()
    assert f"合规过滤日度摘要 — {today}" in summary
    assert "抓取条目总数：**3**" in summary
    assert "拦截（block）：**1**" in summary
    assert "保证" in summary  # 被 block 的标题出现


def test_block_rate_warn_threshold_respected(tmp_path, monkeypatch, capsys, load_module):
    """拦截率超过阈值应在 stderr 输出 WARN。"""
    module = load_module("compliance_filter")

    monkeypatch.setattr(module, "SKILL_DIR", str(tmp_path))

    rules = module.load_rules()
    rules.setdefault("runtime", {})
    rules["runtime"]["block_rate_warn_threshold"] = 0.2  # 20% 阈值
    rules["runtime"]["audit_log_path"] = "audit_{date}.jsonl"
    rules["runtime"]["daily_summary_path"] = "summary_{date}.md"

    # 构造 50% 拦截率：2 正常 + 2 违规
    items = [
        {"title": "宁德时代业绩预告", "url": "u", "source": "s"},
        {"title": "百济神州盈利", "url": "u", "source": "s"},
        {"title": "保证稳赚不赔", "url": "u", "source": "s"},
        {"title": "台独挑衅言论", "url": "u", "source": "s"},
    ]
    kept, blocked, stats = module.filter_batch(items, rules)
    assert stats.block_rate == 0.5  # 2/4

    module.write_audit(
        blocked, kept, stats,
        run_context={"trigger": "threshold_test"},
        log_dir=str(tmp_path),
        rules=rules,
    )

    captured = capsys.readouterr()
    assert "超过阈值" in captured.err
    assert "50" in captured.err  # "拦截率 50.0%"


def test_rules_yaml_is_valid(load_module):
    """基本一致性：rules 文件可加载，每个 pattern 正则可编译。"""
    module = load_module("compliance_filter")
    rules = module.load_rules()

    # 基础结构
    assert "sensitive_keywords" in rules
    assert "investment_red_lines" in rules
    assert "noise_patterns" in rules

    # 正则预编译已完成
    for rl in rules.get("investment_red_lines", []):
        assert "_compiled" in rl
        assert isinstance(rl["_compiled"], re.Pattern)
    for np in rules.get("noise_patterns", []):
        assert "_compiled" in np

    # sensitive_keywords 每组有 category + keywords
    for group in rules.get("sensitive_keywords", []):
        assert "category" in group
        assert "keywords" in group
        assert len(group["keywords"]) > 0
