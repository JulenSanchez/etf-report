import runpy
from pathlib import Path



def test_loads_config_and_holdings_from_custom_dir(load_module, temp_config_dir):
    config_manager = load_module("config_manager")

    config = config_manager.ConfigManager(str(temp_config_dir))

    assert config.get_etfs()[0]["code"] == "510000"
    assert config.get_api_config()["sina"]["timeout"] == 5
    assert config.get_holdings("510000")["components"][0]["name"] == "示例股份"


def test_get_returns_default_for_missing_or_invalid_paths(load_module, temp_config_dir):
    config_manager = load_module("config_manager")
    config = config_manager.ConfigManager(str(temp_config_dir))

    config._config["flat"] = "value"

    assert config.get("api.sina.timeout") == 5
    assert config.get("api.sina.not_exists", "fallback") == "fallback"
    assert config.get("flat.key", "fallback") == "fallback"
    assert config.get("missing.path", 123) == 123


def test_reload_picks_up_file_changes(load_module, temp_config_dir):
    config_manager = load_module("config_manager")
    config = config_manager.ConfigManager(str(temp_config_dir))

    config_path = Path(temp_config_dir) / "config.yaml"
    updated_content = config_path.read_text(encoding="utf-8").replace("timeout: 5", "timeout: 12")
    config_path.write_text(updated_content, encoding="utf-8")

    config.reload()

    assert config.get("api.sina.timeout") == 12



def test_get_editorial_content_reads_optional_yaml(load_module, temp_config_dir):
    config_manager = load_module("config_manager")
    config = config_manager.ConfigManager(str(temp_config_dir))

    (Path(temp_config_dir) / "editorial_content.yaml").write_text(
        'content_date: "2026-04-16"\netf_cards:\n  "510000":\n    research_cards:\n      - "示例研究卡"\n',
        encoding="utf-8",
    )

    editorial_content = config.get_editorial_content()

    assert editorial_content["content_date"] == "2026-04-16"
    assert editorial_content["etf_cards"]["510000"]["research_cards"][0] == "示例研究卡"


def test_validate_returns_false_when_required_sections_missing(load_module, temp_config_dir):

    config_manager = load_module("config_manager")
    config = config_manager.ConfigManager(str(temp_config_dir))

    config._config = {"etfs": [{"code": "510000", "name": "示例ETF"}]}
    assert config.validate() is False

    config._config = {"etfs": []}
    assert config.validate() is False


def test_get_config_returns_singleton_instance(load_module, temp_config_dir):
    config_manager = load_module("config_manager")

    first = config_manager.get_config(str(temp_config_dir))
    second = config_manager.get_config()

    assert first is second


def test_validate_returns_true_for_complete_config(load_module, temp_config_dir):
    config_manager = load_module("config_manager")
    config = config_manager.ConfigManager(str(temp_config_dir))

    assert config.validate() is True
    assert config.get_etf_codes() == ["510000"]
    assert config.get_system_check_config() == {}
    assert config.get_transaction_config() == {}



def test_validate_returns_false_when_etf_missing_code_or_name(load_module, temp_config_dir):
    config_manager = load_module("config_manager")
    config = config_manager.ConfigManager(str(temp_config_dir))

    config._config = {"etfs": [{"name": "缺代码ETF"}], "api": {"sina": {}}, "files": {"data_dir": "data"}}
    assert config.validate() is False

    config._config = {"etfs": [{"code": "510000"}], "api": {"sina": {}}, "files": {"data_dir": "data"}}
    assert config.validate() is False



def test_load_config_falls_back_to_empty_config_on_error(load_module, tmp_path):
    config_manager = load_module("config_manager")
    missing_dir = tmp_path / "missing-config-dir"

    config = config_manager.ConfigManager(str(missing_dir))

    assert config.get_etfs() == []
    assert config.get_api_config() == {}



def test_module_main_runs_without_error():
    runpy.run_module("config_manager", run_name="__main__")

