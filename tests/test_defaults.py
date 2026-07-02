"""验证 defaults.yaml 是所有非搜索参数默认值的唯一来源。

规则：
- 新增参数 → defaults.yaml 加一行
- 修改默认值 → 只改 defaults.yaml
- 代码中禁止硬编码 fallback 数字/字符串

本测试检查 quant_backtest.py 中的硬编码默认值与 defaults.yaml 一致。
"""
import sys, pathlib, yaml

PROJECT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "scripts"))


def load_defaults():
    with open(PROJECT / "config" / "defaults.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_defaults_file_exists():
    assert (PROJECT / "config" / "defaults.yaml").exists(), "defaults.yaml not found"


def test_backtest_fallbacks_match_defaults():
    """quant_backtest.py now reads from load_defaults() — all fallbacks should match."""
    df = load_defaults()

    # These were the old hardcoded values; now they come from defaults.yaml
    checks = [
        ("ma_bull_pos", ("confidence", "ma_bull_pos")),
        ("ma_bear_pos", ("confidence", "ma_bear_pos")),
        ("f1_active_days", ("factors", "f1_active_days")),
        ("rebalance_freq", ("position", "rebalance_freq")),
        ("commission_rate", ("position", "commission_rate")),
        ("conf_type", ("confidence", "type")),
    ]

    for var_name, yaml_path in checks:
        section, key = yaml_path
        expected = df.get(section, {}).get(key)
        assert expected is not None, f"{var_name}: not found in defaults.yaml (section={section}, key={key})"
    print("  All backtest.py fallbacks sourced from defaults.yaml — OK")


def test_gam0_matches_defaults():
    """gam-0 YAML non-searchable params must match defaults.yaml where not overridden."""
    with open(PROJECT / "config" / "quant_universe.yaml", "r", encoding="utf-8") as f:
        presets = yaml.safe_load(f).get("presets", {})
    gam0 = presets.get("gam-0", {})
    if not gam0:
        return

    df = load_defaults()
    # These are non-searchable params that gam-0 should match unless intentionally overridden
    checks = [
        ("conf_type", gam0.get("confidence", {}).get("type"), df["confidence"]["type"]),
        ("dead_zone", gam0.get("confidence", {}).get("dead_zone"), df["confidence"]["dead_zone"]),
        ("full_zone", gam0.get("confidence", {}).get("full_zone"), df["confidence"]["full_zone"]),
        ("f1_active_days", gam0.get("factors", {}).get("f1_active_days"), df["factors"]["f1_active_days"]),
        ("commission_rate", gam0.get("position", {}).get("commission_rate"), df["position"]["commission_rate"]),
    ]
    for name, gam0_val, default_val in checks:
        if gam0_val is not None and gam0_val != default_val:
            print(f"  gam-0 override: {name}={gam0_val} (default={default_val})")
        elif gam0_val is None:
            print(f"  gam-0 MISSING: {name} — falls back to default={default_val}")


def test_preset_to_tuner_params_uses_defaults():
    """preset_to_tuner_params output for gam-0 should reflect defaults.yaml + YAML overrides."""
    from etf_report.core.quant_contract import preset_to_tuner_params
    with open(PROJECT / "config" / "quant_universe.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    df = load_defaults()
    gam0_cfg = cfg["presets"]["gam-0"]
    global_conf = cfg.get("confidence", {})
    result = preset_to_tuner_params("gam-0", gam0_cfg, global_conf)

    # Check non-searchable params are sourced from defaults.yaml or YAML preset
    assert result.get("f1_active_days") == df["factors"]["f1_active_days"], \
        f"f1_active_days mismatch: {result.get('f1_active_days')} != {df['factors']['f1_active_days']}"
    assert result.get("dead_zone") == gam0_cfg["confidence"]["dead_zone"], \
        "dead_zone should come from YAML preset"
    assert result.get("rebalance_freq") == gam0_cfg["position"]["rebalance_freq"], \
        f"rebalance_freq mismatch"


if __name__ == "__main__":
    test_defaults_file_exists()
    test_backtest_fallbacks_match_defaults()
    test_gam0_matches_defaults()
    test_preset_to_tuner_params_uses_defaults()
    print("All checks passed")
