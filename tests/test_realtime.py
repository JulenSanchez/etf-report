import json

import pytest



@pytest.mark.parametrize(
    ("change", "with_sign", "expected_text", "expected_color"),
    [
        (1.23, True, "+1.23%", "#10b981"),
        (-2.5, True, "-2.50%", "#ef4444"),
        (0, True, "0.00%", "#9ca3af"),
        (1.23, False, "1.23%", "#10b981"),
        (None, True, "--", "#9ca3af"),
    ],
)
def test_format_change_html(load_module, change, with_sign, expected_text, expected_color):
    module = load_module("realtime_data_updater")

    text, color = module.format_change_html(change, with_sign=with_sign)

    assert text == expected_text
    assert color == expected_color


def test_fetch_realtime_quote_sina_parses_a_share_and_hk(monkeypatch, load_module, fake_response_factory):
    module = load_module("realtime_data_updater")
    response_text = "\n".join(
        [
            'var hq_str_sh000001="上证指数,0,100.00,103.00";',
            'var hq_str_rt_hk00700="ignored,腾讯控股,ignored,300.00,ignored,ignored,330.00,ignored,ignored";',
        ]
    )

    monkeypatch.setattr(
        module.requests,
        "get",
        lambda *args, **kwargs: fake_response_factory(text=response_text),
    )

    result = module.fetch_realtime_quote_sina(["sh000001", "hk00700"])

    assert result["sh000001"]["name"] == "上证指数"
    assert result["sh000001"]["change_pct"] == 3.0
    assert result["hk00700"]["name"] == "腾讯控股"
    assert result["hk00700"]["change_pct"] == 10.0


def test_fetch_realtime_quote_sina_returns_empty_on_error(monkeypatch, load_module):
    module = load_module("realtime_data_updater")

    def _raise(*args, **kwargs):
        raise RuntimeError("network error")

    monkeypatch.setattr(module.requests, "get", _raise)

    assert module.fetch_realtime_quote_sina(["sh000001"]) == {}


def test_resolve_total_ratio_prefers_positive_value_and_falls_back_to_components(load_module):
    module = load_module("realtime_data_updater")

    holdings = [
        {"name": "示例一", "ratio": 12.5},
        {"name": "示例二", "ratio": 7.5},
    ]

    assert module.resolve_total_ratio(25.0, holdings) == 25.0
    assert module.resolve_total_ratio(0, holdings) == 20.0
    assert module.resolve_total_ratio(None, holdings) == 20.0



def test_fetch_all_realtime_data_fills_missing_holding_quote_with_none(monkeypatch, load_module):
    module = load_module("realtime_data_updater")
    monkeypatch.setattr(module.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        module,
        "ETF_CONFIG",
        {
            "510000": {
                "name": "示例ETF",
                "market": "sh",
                "holdings": [
                    {"market": "sh", "code": "600000", "name": "浦发银行", "ratio": 5.0}
                ],
                "total_ratio": 5.0,
            }
        },
    )
    monkeypatch.setattr(
        module,
        "fetch_realtime_quote_sina",
        lambda _symbols: {"sh510000": {"name": "示例ETF", "price": 1.0, "change_pct": 1.2}},
    )

    result = module.fetch_all_realtime_data()

    assert result["510000"]["etf_change"] == 1.2
    assert result["510000"]["holdings"][0]["change"] is None
    assert result["510000"]["total_ratio"] == 5.0



def test_fetch_realtime_quote_sina_returns_empty_for_empty_symbols(load_module):
    module = load_module("realtime_data_updater")

    assert module.fetch_realtime_quote_sina([]) == {}


def test_update_html_etf_change_updates_panel_value(tmp_path, load_module):
    module = load_module("realtime_data_updater")
    html_file = tmp_path / "index.html"
    html_file.write_text(
        '<div id="panel-510000"><div class="info-label">日涨跌幅</div><div class="info-value">旧值</div></div>',
        encoding="utf-8",
    )

    module.update_html_etf_change(str(html_file), {"510000": {"name": "示例ETF", "etf_change": 1.23}})

    updated = html_file.read_text(encoding="utf-8")
    assert "+1.23%" in updated
    assert "text-green" in updated



def test_update_html_holdings_pie_replaces_data_array_and_adds_other(tmp_path, load_module):
    module = load_module("realtime_data_updater")
    html_file = tmp_path / "index.html"
    html_file.write_text(
        "<script>const data = [{ name: '旧', value: 100, change: '--', changeColor: '#9ca3af' }];"
        "const chart = document.getElementById('holdings-chart-510000');</script>",

        encoding="utf-8",
    )

    module.update_html_holdings_pie(
        str(html_file),
        {
            "510000": {
                "name": "示例ETF",
                "total_ratio": 30.0,
                "holdings": [{"name": "宁德时代", "ratio": 30.0, "change": 2.5}],
            }
        },
    )

    updated = html_file.read_text(encoding="utf-8")
    assert "宁德时代" in updated
    assert "其他" in updated
    assert "+2.50%" in updated


def test_save_realtime_data_writes_json(tmp_path, load_module):
    module = load_module("realtime_data_updater")
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    module.save_realtime_data({"510000": {"etf_change": 1.2}}, str(data_dir))

    saved = json.loads((data_dir / "etf_realtime_data.json").read_text(encoding="utf-8"))
    assert saved["510000"]["etf_change"] == 1.2


def test_update_js_realtime_data_replaces_const_block(tmp_path, load_module):
    module = load_module("realtime_data_updater")
    js_file = tmp_path / "main.js"
    js_file.write_text('const realtimeData = {"old": 1};\nconst other = 1;', encoding="utf-8")

    module.update_js_realtime_data(str(js_file), {"510000": {"etf_change": 1.23}})

    updated = js_file.read_text(encoding="utf-8")
    assert 'const realtimeData = {' in updated
    assert '"etf_change": 1.23' in updated
    assert '"old": 1' not in updated

