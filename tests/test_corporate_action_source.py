from datetime import date
import json


def test_get_window_years_covers_cross_year_window(load_module):
    module = load_module("corporate_action_source")

    assert module.get_window_years(date(2024, 12, 1), date(2026, 4, 15)) == [2024, 2025, 2026]


def test_normalize_fund_split_row_maps_supported_types(load_module):
    module = load_module("corporate_action_source")
    row = {
        "基金代码": "515880",
        "基金简称": "通信设备ETF",
        "拆分折算日": "2026-02-03",
        "拆分类型": "份额分拆",
        "拆分折算": 3.0,
    }

    event = module.normalize_fund_split_row(
        row,
        {"515880"},
        date(2026, 1, 1),
        date(2026, 4, 15),
    )

    assert event == {
        "code": "515880",
        "fund_name": "通信设备ETF",
        "action": "share_split",
        "ex_date": "2026-02-03",
        "ratio": 3.0,
        "raw_type": "份额分拆",
        "source": "akshare.fund_cf_em",
        "note": "自动识别到份额分拆，每份变动比例 3.0",
    }



def test_detect_corporate_action_events_filters_window_and_deduplicates(monkeypatch, load_module):
    module = load_module("corporate_action_source")

    rows_by_year = {
        2025: [
            {
                "基金代码": "515880",
                "基金简称": "通信设备ETF",
                "拆分折算日": "2025-12-20",
                "拆分类型": "份额分拆",
                "拆分折算": 2.0,
            },
            {
                "基金代码": "159566",
                "基金简称": "储能电池ETF",
                "拆分折算日": "2025-11-01",
                "拆分类型": "份额折算",
                "拆分折算": 0.5,
            },
        ],
        2026: [
            {
                "基金代码": "515880",
                "基金简称": "通信设备ETF",
                "拆分折算日": "2026-02-03",
                "拆分类型": "份额分拆",
                "拆分折算": 3.0,
            },
            {
                "基金代码": "515880",
                "基金简称": "通信设备ETF",
                "拆分折算日": "2026-02-03",
                "拆分类型": "份额分拆",
                "拆分折算": 3.0,
            },
        ],
    }

    monkeypatch.setattr(module, "fetch_fund_split_rows", lambda year, detection_config=None: rows_by_year.get(year, []))

    payload = module.detect_corporate_action_events(
        ["515880", "159566"],
        date(2026, 1, 1),
        date(2026, 4, 15),
        {},
    )

    assert payload["window"]["years"] == [2026]
    assert payload["events_by_code"] == {
        "515880": [
            {
                "fund_name": "通信设备ETF",
                "action": "share_split",
                "ex_date": "2026-02-03",
                "ratio": 3.0,
                "raw_type": "份额分拆",
                "source": "akshare.fund_cf_em",
                "note": "自动识别到份额分拆，每份变动比例 3.0",
            }
        ]
    }


def test_save_detected_corporate_action_payload_writes_json(tmp_path, load_module):
    module = load_module("corporate_action_source")
    output_path = tmp_path / "data" / "corporate_action_events.json"
    payload = {
        "generated_at": "2026-04-15 17:00:00",
        "window": {"start_date": "2026-01-01", "end_date": "2026-04-15", "years": [2026]},
        "source": "akshare.fund_cf_em",
        "events_by_code": {"515880": [{"action": "share_split", "ex_date": "2026-02-03", "ratio": 3.0}]},
    }

    module.save_detected_corporate_action_payload(payload, str(output_path))

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["events_by_code"]["515880"][0]["ratio"] == 3.0
