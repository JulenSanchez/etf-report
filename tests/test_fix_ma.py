import json
from datetime import datetime



def _build_kline_data(count: int):

    dates = [f"2026-01-{i:02d}" for i in range(1, count + 1)]
    kline = [[price, price, price - 0.5, price + 0.5] for price in range(1, count + 1)]
    return {
        "dates": dates,
        "kline": kline,
        "volumes": list(range(100, 100 + count)),
        "latest_close": float(count),
        "latest_change": 1.23,
    }


def test_calculate_ma_returns_expected_values(load_module):
    module = load_module("fix_ma_and_benchmark")
    kline = [[1, 1, 0, 2], [2, 2, 1, 3], [3, 3, 2, 4], [4, 4, 3, 5]]

    assert module.calculate_ma(kline, 3) == [None, None, 2.0, 3.0]


def test_trim_data_with_ma_keeps_display_window_and_ma(load_module):
    module = load_module("fix_ma_and_benchmark")
    data = _build_kline_data(30)

    trimmed = module.trim_data_with_ma(data, warmup_days=19, display_days=5)
    expected_ma5 = module.calculate_ma(data["kline"], 5)[-5:]
    expected_ma20 = module.calculate_ma(data["kline"], 20)[-5:]

    assert len(trimmed["dates"]) == 5
    assert trimmed["dates"][0] == data["dates"][-5]
    assert trimmed["ma5"] == expected_ma5
    assert trimmed["ma20"] == expected_ma20


def test_trim_data_with_ma_returns_original_when_insufficient(load_module):
    module = load_module("fix_ma_and_benchmark")
    data = _build_kline_data(10)

    trimmed = module.trim_data_with_ma(data, warmup_days=19, display_days=5)

    assert trimmed == data


def test_trim_benchmark_data_rebases_from_trimmed_first_day(load_module):
    module = load_module("fix_ma_and_benchmark")
    benchmark = {
        "dates": [f"2026-01-{i:02d}" for i in range(1, 11)],
        "closes": [100, 102, 104, 103, 106, 108, 110, 111, 113, 115],
        "kline": [[1, 1, 1, 1] for _ in range(10)],
        "normalized": [],
    }

    trimmed = module.trim_benchmark_data(benchmark, warmup_days=2, display_days=4)

    assert trimmed["dates"] == benchmark["dates"][-4:]
    assert trimmed["normalized"][0] == 0.0
    assert trimmed["normalized"][-1] == round((115 / 110 - 1) * 100, 2)


def test_fetch_kline_sina_parses_response(monkeypatch, load_module, fake_response_factory):
    module = load_module("fix_ma_and_benchmark")
    payload = [
        {"day": "2026-01-01", "open": "10", "close": "10", "low": "9", "high": "11", "volume": "1000"},
        {"day": "2026-01-02", "open": "10", "close": "11", "low": "10", "high": "12", "volume": "1200"},
    ]

    monkeypatch.setattr(module.requests, "get", lambda *args, **kwargs: fake_response_factory(json_data=payload))

    result = module.fetch_kline_sina("sh510000", scale=240, days=2)

    assert result["dates"] == ["2026-01-01", "2026-01-02"]
    assert result["kline"][1] == [10.0, 11.0, 10.0, 12.0]
    assert result["latest_close"] == 11.0
    assert result["latest_change"] == 10.0



def test_trim_incomplete_daily_bar_drops_today_before_market_close(load_module):
    module = load_module("fix_ma_and_benchmark")
    payload = [
        {"day": "2026-04-15", "open": "10", "close": "10.5", "low": "9.8", "high": "10.6", "volume": "1000"},
        {"day": "2026-04-16", "open": "10.6", "close": "10.8", "low": "10.5", "high": "10.9", "volume": "800"},
    ]

    trimmed = module.trim_incomplete_daily_bar(
        payload,
        "sh510000",
        240,
        now=datetime(2026, 4, 16, 10, 30),
    )

    assert [item["day"] for item in trimmed] == ["2026-04-15"]



def test_fetch_index_data_sina_normalizes_response(monkeypatch, load_module, fake_response_factory):
    module = load_module("fix_ma_and_benchmark")
    payload = [
        {"day": "2026-01-01", "open": "100", "close": "100", "low": "99", "high": "101"},
        {"day": "2026-01-02", "open": "102", "close": "110", "low": "101", "high": "111"},
    ]

    monkeypatch.setattr(module.requests, "get", lambda *args, **kwargs: fake_response_factory(json_data=payload))

    result = module.fetch_index_data_sina("sh000300", days=2)

    assert result["dates"] == ["2026-01-01", "2026-01-02"]
    assert result["closes"] == [100.0, 110.0]
    assert result["normalized"] == [0.0, 10.0]


def test_apply_split_adjustments_rebases_pre_split_prices(load_module):
    module = load_module("fix_ma_and_benchmark")
    data = {
        "dates": ["2026-02-02", "2026-02-03"],
        "kline": [[3.287, 3.16, 3.15, 3.344], [1.074, 1.084, 1.046, 1.095]],
        "volumes": [100, 200],
        "latest_close": 1.084,
        "latest_change": -65.7,
    }

    adjusted = module.apply_split_adjustments(data, [{"ex_date": "2026-02-03", "ratio": 3.0}])

    assert adjusted["kline"][0] == [1.096, 1.053, 1.05, 1.115]
    assert adjusted["kline"][1] == [1.074, 1.084, 1.046, 1.095]
    assert adjusted["volumes"] == [300, 200]
    assert adjusted["latest_change"] == 2.94



def test_apply_split_adjustments_covers_detected_last_pre_event_day(load_module):
    module = load_module("fix_ma_and_benchmark")
    data = {
        "dates": ["2026-02-02", "2026-02-03"],
        "kline": [[3.287, 3.16, 3.15, 3.344], [1.074, 1.084, 1.046, 1.095]],
        "volumes": [100, 200],
        "latest_close": 1.084,
        "latest_change": -65.7,
    }

    adjusted = module.apply_split_adjustments(data, [{"ex_date": "2026-02-02", "ratio": 3.0}])

    assert adjusted["kline"][0] == [1.096, 1.053, 1.05, 1.115]
    assert adjusted["kline"][1] == [1.074, 1.084, 1.046, 1.095]
    assert adjusted["volumes"] == [300, 200]



def test_build_weekly_from_daily_recomputes_split_week(load_module):
    module = load_module("fix_ma_and_benchmark")
    daily = {
        "dates": ["2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06"],
        "kline": [
            [1.096, 1.053, 1.05, 1.115],
            [1.074, 1.084, 1.046, 1.095],
            [1.061, 1.051, 1.029, 1.075],
            [1.03, 1.025, 1.018, 1.044],
            [1.008, 1.017, 1.004, 1.04],
        ],
        "volumes": [300, 200, 180, 160, 140],
        "latest_close": 1.017,
        "latest_change": 0.89,
    }

    weekly = module.build_weekly_from_daily(daily)

    assert weekly["dates"] == ["2026-02-06"]
    assert weekly["kline"] == [[1.096, 1.017, 1.004, 1.115]]
    assert weekly["volumes"] == [980]
    assert weekly["latest_close"] == 1.017
    assert weekly["latest_change"] == 0





def test_update_html_legend_selected_inserts_selected_config(tmp_path, load_module):
    module = load_module("fix_ma_and_benchmark")
    html_file = tmp_path / "index.html"
    html_file.write_text("legend: { data: legendData, }", encoding="utf-8")

    assert module.update_html_legend_selected(str(html_file)) is True
    assert "selected: { '沪深300': false }" in html_file.read_text(encoding="utf-8")


def test_update_html_legend_selected_returns_true_when_config_already_exists(tmp_path, load_module):
    module = load_module("fix_ma_and_benchmark")
    html_file = tmp_path / "index.html"
    html_file.write_text("selected: { '沪深300': false }", encoding="utf-8")

    assert module.update_html_legend_selected(str(html_file)) is True


def test_get_data_cleaning_events_prefers_detected_events_and_skips_manual_fallback(load_module, monkeypatch):
    module = load_module("fix_ma_and_benchmark")
    monkeypatch.setattr(module, "DATA_CLEANING_EVENTS", {
        "515880": [{"action": "share_split", "ex_date": "2026-02-03", "ratio": 3.0, "note": "manual"}]
    })
    monkeypatch.setattr(module, "LEGACY_SPLIT_EVENTS", {
        "515880": [{"ex_date": "2026-01-15", "ratio": 2.0}]
    })

    events = module.get_data_cleaning_events("515880", {
        "515880": [{"action": "share_split", "ex_date": "2026-02-02", "ratio": 3.0, "note": "detected"}]
    })

    assert events == [
        {"action": "share_split", "ex_date": "2026-02-02", "ratio": 3.0, "note": "detected"},
    ]





def test_sync_corporate_action_events_persists_detected_payload(tmp_path, monkeypatch, load_module):
    module = load_module("fix_ma_and_benchmark")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    payload = {
        "generated_at": "2026-04-15 17:00:00",
        "window": {"start_date": "2026-01-01", "end_date": "2026-04-15", "years": [2026]},
        "source": "akshare.fund_cf_em",
        "events_by_code": {"515880": [{"action": "share_split", "ex_date": "2026-02-03", "ratio": 3.0}]},
    }
    captured = {}

    monkeypatch.setattr(module, "ETF_LIST", [{"code": "515880"}])
    monkeypatch.setattr(module, "AUTO_DETECTION_CONFIG", {"enabled": True, "lookback_calendar_days": 120})
    monkeypatch.setattr(module, "detect_corporate_action_events", lambda etf_codes, start_date, end_date, detection_config=None: payload)
    monkeypatch.setattr(module, "save_detected_corporate_action_payload", lambda saved_payload, output_path: captured.update({"payload": saved_payload, "path": output_path}))

    result = module.sync_corporate_action_events(str(data_dir), reference_date=datetime(2026, 4, 15).date())

    assert result == payload["events_by_code"]
    assert captured["payload"] == payload
    assert captured["path"].endswith("corporate_action_events.json")



def test_main_writes_data_file_and_updates_js(tmp_path, monkeypatch, load_module):
    """BUG-013 后 fix_ma_and_benchmark.main() 不再写 outputs/js/main.js，
    仅产出 data/etf_full_kline_data.json；保留测试函数名以记录历史契约。
    """

    module = load_module("fix_ma_and_benchmark")
    scripts_dir = tmp_path / "scripts"
    outputs_js_dir = tmp_path / "outputs" / "js"
    data_dir = tmp_path / "data"
    scripts_dir.mkdir()
    outputs_js_dir.mkdir(parents=True)
    data_dir.mkdir()

    # 即便该目录下存在老版 main.js，BUG-013 后 main() 也不会再触碰它
    js_file = outputs_js_dir / "main.js"
    js_file.write_text('const klineData = {"old": 1};', encoding="utf-8")

    monkeypatch.setattr(module, "__file__", str(scripts_dir / "fix_ma_and_benchmark.py"))
    monkeypatch.setattr(module, "DISPLAY_DAYS", 5)
    monkeypatch.setattr(module, "MA_WARMUP_DAYS", 2)
    monkeypatch.setattr(module, "FETCH_DAYS", 7)
    monkeypatch.setattr(module, "DISPLAY_WEEKS", 5)
    monkeypatch.setattr(module, "MA_WARMUP_WEEKS", 2)
    monkeypatch.setattr(module, "FETCH_WEEKS", 7)
    monkeypatch.setattr(
        module,
        "ETF_LIST",
        [
            {
                "code": "510000",
                "name": "示例ETF",
                "market": "sh",
                "benchmark": {"name": "沪深300", "code": "sh000300"},
            }
        ],
    )
    monkeypatch.setattr(module.time, "sleep", lambda *_args, **_kwargs: None)

    daily = _build_kline_data(30)
    benchmark = {
        "dates": [f"2026-01-{i:02d}" for i in range(1, 31)],
        "closes": [100 + i for i in range(30)],
        "kline": [[100 + i, 100 + i, 99 + i, 101 + i] for i in range(30)],
        "normalized": [float(i) for i in range(30)],
    }

    monkeypatch.setattr(module, "fetch_kline_sina", lambda _symbol, scale=240, days=60: daily)
    monkeypatch.setattr(module, "fetch_index_data_sina", lambda _symbol, days=60: benchmark)

    result = module.main()

    assert "510000" in result
    assert "weekly" in result["510000"]
    assert result["510000"]["weekly"]["dates"]
    saved_json = data_dir / "etf_full_kline_data.json"

    assert saved_json.exists()
    assert "示例ETF" in saved_json.read_text(encoding="utf-8")
    # BUG-013：outputs/js/main.js 不再被主流程写入，保留原文件内容不变
    assert js_file.read_text(encoding="utf-8") == 'const klineData = {"old": 1};'


def test_main_falls_back_to_previous_data_when_fetch_fails(tmp_path, monkeypatch, load_module):
    module = load_module("fix_ma_and_benchmark")
    scripts_dir = tmp_path / "scripts"
    outputs_js_dir = tmp_path / "outputs" / "js"
    data_dir = tmp_path / "data"
    scripts_dir.mkdir()
    outputs_js_dir.mkdir(parents=True)
    data_dir.mkdir()

    js_file = outputs_js_dir / "main.js"
    js_file.write_text('const klineData = {"old": 1};', encoding="utf-8")

    previous_entry = {
        "name": "示例ETF",
        "benchmark_name": "沪深300",
        "daily": _build_kline_data(8),
        "weekly": _build_kline_data(4),
        "benchmark": {
            "dates": [f"2026-01-{i:02d}" for i in range(1, 9)],
            "closes": [100 + i for i in range(8)],
            "kline": [[100 + i, 100 + i, 99 + i, 101 + i] for i in range(8)],
            "normalized": [float(i) for i in range(8)],
        },
        "etf_normalized": [float(i) for i in range(8)],
    }
    (data_dir / "etf_full_kline_data.json").write_text('{\n  "510000": ' + json.dumps(previous_entry, ensure_ascii=False, indent=2) + '\n}', encoding="utf-8")


    monkeypatch.setattr(module, "__file__", str(scripts_dir / "fix_ma_and_benchmark.py"))
    monkeypatch.setattr(module, "DISPLAY_DAYS", 5)
    monkeypatch.setattr(module, "MA_WARMUP_DAYS", 2)
    monkeypatch.setattr(module, "FETCH_DAYS", 7)
    monkeypatch.setattr(module, "DISPLAY_WEEKS", 5)
    monkeypatch.setattr(module, "MA_WARMUP_WEEKS", 2)
    monkeypatch.setattr(module, "FETCH_WEEKS", 7)
    monkeypatch.setattr(
        module,
        "ETF_LIST",
        [
            {
                "code": "510000",
                "name": "示例ETF",
                "market": "sh",
                "benchmark": {"name": "沪深300", "code": "sh000300"},
            }
        ],
    )
    monkeypatch.setattr(module.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "fetch_kline_sina", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "fetch_index_data_sina", lambda *_args, **_kwargs: None)

    result = module.main()

    assert result["510000"]["daily"] == previous_entry["daily"]
    assert result["510000"]["weekly"] == previous_entry["weekly"]
    assert result["510000"]["benchmark"] == previous_entry["benchmark"]
    base = previous_entry["daily"]["kline"][0][1]
    expected_normalized = [round((k[1] / base - 1) * 100, 2) for k in previous_entry["daily"]["kline"]]
    assert result["510000"]["etf_normalized"] == expected_normalized




