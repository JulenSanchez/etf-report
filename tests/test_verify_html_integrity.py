import types
from datetime import datetime


def test_load_etf_codes_prefers_config(monkeypatch, load_module):
    module = load_module("verify_html_integrity")
    fake_config = types.SimpleNamespace(
        get=lambda key: ["159865"] if key == "system_check.etf_codes" else None,
        get_etf_codes=lambda: ["510000"],
    )

    monkeypatch.setattr(module, "get_config", lambda: fake_config)

    assert module.load_etf_codes() == ["159865"]


def test_load_etf_codes_falls_back_to_defaults(load_module):
    module = load_module("verify_html_integrity")

    module.get_config = None

    assert module.load_etf_codes() == module.DEFAULT_ETF_CODES



def test_check_editorial_metadata_passes_when_inline_dates_exist(monkeypatch, load_module):
    module = load_module("verify_html_integrity")
    fake_config = types.SimpleNamespace(
        get_editorial_content=lambda: {
            "content_date": "2026-04-10",
            "etf_cards": {
                "510000": {
                    "freshness_policy": "manual_daily",
                    "research_cards": ["研究卡一"],
                },
            },
            "macro_cards": {
                "domestic-policy-card": {
                    "freshness_policy": "sticky",
                    "content_date": "2026-04-08",
                    "items": ["宏观条目一"],
                },
            },
        }
    )
    monkeypatch.setattr(module, "get_config", lambda: fake_config)

    result = module.check_editorial_metadata(
        '数据截止: 2026-04-10\n'
        '<span id="research-date-510000-1">2026-04-10</span>'
        '<span id="editorial-date-domestic-policy-card-1">2026-04-08</span>'
    )

    assert result[0]["status"] == "PASS"



def test_check_date_consistency_supports_nested_header_values(load_module):
    module = load_module("verify_html_integrity")
    today_iso = datetime.now().strftime("%Y-%m-%d")
    today_cn = datetime.now().strftime("%Y年%m月%d日")

    result = module.check_date_consistency(
        f'报告日期: <strong class="text-blue" id="report-date-value">{today_cn}</strong>'
        f'<span id="report-cutoff-label">数据截止:</span> <span id="report-cutoff-value">{today_iso}</span>'
        f'生成时间: {today_iso}'
    )

    assert [item["status"] for item in result] == ["PASS", "PASS", "PASS"]



def test_check_debug_id_coverage_passes_when_required_ids_exist(monkeypatch, load_module):
    module = load_module("verify_html_integrity")
    fake_config = types.SimpleNamespace(
        get_editorial_content=lambda: {
            "macro_cards": {
                "domestic-policy-card": {"items": ["条目一", "条目二"]},
                "global-news-card": {"items": ["条目一"]},
                "market-sentiment-card": {"items": ["条目一"]},
            }
        }
    )
    monkeypatch.setattr(module, "get_config", lambda: fake_config)

    ids = module._collect_debug_target_ids()
    assert "report-market-badge-text" in ids
    assert "report-date-value" in ids
    assert "market-rotation-stat-leader-value" in ids
    assert "leaders-top5-table-change-1" in ids

    html = ''.join(f'<div id="{element_id}"></div>' for element_id in ids)
    result = module.check_debug_id_coverage(html)

    assert result[0]["status"] == "PASS"



def test_check_debug_id_coverage_fails_when_required_id_missing(monkeypatch, load_module):
    module = load_module("verify_html_integrity")
    fake_config = types.SimpleNamespace(
        get_editorial_content=lambda: {
            "macro_cards": {
                "domestic-policy-card": {"items": ["条目一"]},
                "global-news-card": {"items": ["条目一"]},
                "market-sentiment-card": {"items": ["条目一"]},
            }
        }
    )
    monkeypatch.setattr(module, "get_config", lambda: fake_config)

    ids = module._collect_debug_target_ids()
    html = ''.join(f'<div id="{element_id}"></div>' for element_id in ids if element_id != "fund-flow-meta")
    result = module.check_debug_id_coverage(html)

    assert result[0]["status"] == "FAIL"
    assert "fund-flow-meta" in result[0]["detail"]




