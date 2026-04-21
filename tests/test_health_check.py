import builtins
import types


def test_required_data_files_excludes_fund_flow(load_module):
    module = load_module("health_check")

    assert module.REQUIRED_DATA_FILES == [
        "etf_full_kline_data.json",
        "etf_realtime_data.json",
    ]


def test_check_required_imports_uses_real_import_names(monkeypatch, load_module):
    module = load_module("health_check")
    attempted = []
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        attempted.append(name)
        if name in {"requests", "yaml"}:
            return types.SimpleNamespace(__name__=name)
        if name == "beautifulsoup4":
            raise ImportError("should not import package distribution name")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = module.DependencyChecker.check_required_imports()

    assert result.status == "PASS"
    assert "beautifulsoup4" not in attempted
    assert attempted[:2] == ["requests", "yaml"]


def test_check_js_data_blocks_passes_when_only_kline_data_exists(tmp_path, monkeypatch, load_module):
    """BUG-015 后 D2 优先读 data/runtime_payload.js。此测试验证回退分支：
    当 runtime_payload.js 不存在时，仍能识别老架构 HTML 内联 const klineData。
    """
    module = load_module("health_check")
    html_file = tmp_path / "index.html"
    html_file.write_text('<script>const klineData = {"ok": true};</script>', encoding="utf-8")

    # 将 SKILL_DIR 指向 tmp_path，确保 data/runtime_payload.js 不存在，走回退分支
    monkeypatch.setattr(module, "HTML_FILE", str(html_file))
    monkeypatch.setattr(module, "SKILL_DIR", str(tmp_path))

    result = module.HTMLChecker.check_js_data_blocks()

    assert result.status == "PASS"
    assert result.details["source"] == "HTML 内联（兼容模式）"
    assert result.details["required_found"] == ["klineData"]
    assert result.details["optional_missing"] == ["realtimeData"]


def test_check_js_data_blocks_passes_when_runtime_payload_has_both_keys(tmp_path, monkeypatch, load_module):
    """BUG-015 回归保护：D2 应能从 data/runtime_payload.js 读取 klineData/realtimeData。"""
    module = load_module("health_check")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "runtime_payload.js").write_text(
        'window.__ETF_REPORT_RUNTIME__ = {\n'
        '  "klineData": {"510000": {"name": "示例ETF"}},\n'
        '  "realtimeData": {"510000": {"etf_change": 1.23}}\n'
        '};\n',
        encoding="utf-8",
    )
    # HTML 本身不含 const，模拟 REQ-146 后真实产物
    html_file = tmp_path / "index.html"
    html_file.write_text('<script src="./data/runtime_payload.js"></script>', encoding="utf-8")

    monkeypatch.setattr(module, "HTML_FILE", str(html_file))
    monkeypatch.setattr(module, "SKILL_DIR", str(tmp_path))

    result = module.HTMLChecker.check_js_data_blocks()

    assert result.status == "PASS"
    assert result.details["source"] == "runtime_payload.js"
    assert result.details["required_found"] == ["klineData"]
    assert result.details["optional_found"] == ["realtimeData"]


def test_check_file_sizes_accepts_current_html_scale(tmp_path, monkeypatch, load_module):
    module = load_module("health_check")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    html_file = tmp_path / "index.html"

    html_file.write_text("A" * (250 * 1024), encoding="utf-8")
    (data_dir / "etf_full_kline_data.json").write_text("B" * (120 * 1024), encoding="utf-8")

    # BUG-014：A4 新增了对 REQ-146 抽离的 CSS/JS 和 runtime_payload.js 的检查；
    # 构造齐全的资产目录以避免测试命中"关键外链资源缺失"路径。
    assets_css = tmp_path / "assets" / "css"
    assets_js = tmp_path / "assets" / "js"
    assets_css.mkdir(parents=True)
    assets_js.mkdir(parents=True)
    (assets_css / "report.css").write_text("C" * (20 * 1024), encoding="utf-8")
    (assets_css / "debug.css").write_text("D" * (10 * 1024), encoding="utf-8")
    (assets_js / "chart-lifecycle.js").write_text("E" * (3 * 1024), encoding="utf-8")
    (assets_js / "report-main.js").write_text("F" * (100 * 1024), encoding="utf-8")
    (assets_js / "debug-toolbar.js").write_text("G" * (20 * 1024), encoding="utf-8")
    (data_dir / "runtime_payload.js").write_text("H" * (150 * 1024), encoding="utf-8")

    monkeypatch.setattr(module, "HTML_FILE", str(html_file))
    monkeypatch.setattr(module, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(module, "SKILL_DIR", str(tmp_path))

    result = module.FileChecker.check_file_sizes()

    assert result.status == "PASS"


def test_load_etf_codes_prefers_config(monkeypatch, load_module):
    module = load_module("health_check")
    fake_config = types.SimpleNamespace(
        get=lambda key: ["159865"] if key == "system_check.etf_codes" else None,
        get_etf_codes=lambda: ["510000"],
    )

    monkeypatch.setattr(module, "get_config", lambda: fake_config)

    assert module.load_etf_codes() == ["159865"]



def test_check_editorial_freshness_warns_when_manual_daily_content_is_stale(tmp_path, monkeypatch, load_module):
    module = load_module("health_check")
    html_file = tmp_path / "index.html"
    html_file.write_text('数据截止: 2026-04-10', encoding="utf-8")

    fake_config = types.SimpleNamespace(
        get_editorial_content=lambda: {
            "content_date": "2026-04-09",
            "etf_cards": {
                "510000": {"freshness_policy": "manual_daily"},
            },
            "macro_cards": {
                "domestic-policy-card": {"freshness_policy": "sticky", "content_date": "2026-04-01"},
            },
        }
    )

    monkeypatch.setattr(module, "HTML_FILE", str(html_file))
    monkeypatch.setattr(module, "get_config", lambda: fake_config)

    result = module.WorkflowChecker.check_editorial_freshness()

    assert result.status == "WARN"
    assert result.details["warnings"] == ["research-510000:2026-04-09"]


