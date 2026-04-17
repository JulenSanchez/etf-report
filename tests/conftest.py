import importlib
import os
import sys
import textwrap
from pathlib import Path

import pytest



SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"

for path in (str(SCRIPTS_DIR), str(SKILL_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def reset_config_manager_state() -> None:
    module = sys.modules.get("config_manager")
    if not module:
        return

    module._config_manager = None
    module.ConfigManager._instance = None
    module.ConfigManager._config = None
    module.ConfigManager._config_dir = None
    module.ConfigManager._loaded = False


@pytest.fixture
def load_module():
    original_cwd = os.getcwd()

    def _load(module_name: str, *, fresh: bool = True):
        if fresh:
            sys.modules.pop(module_name, None)
            sys.modules.pop("config_manager", None)
            reset_config_manager_state()
        return importlib.import_module(module_name)

    yield _load
    os.chdir(original_cwd)


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    (config_dir / "config.yaml").write_text(
        textwrap.dedent(
            """
            etfs:
              - code: "510000"
                name: "示例ETF"
                market: "sh"
                benchmark:
                  code: "sh000300"
                  name: "沪深300"

            api:
              sina:
                timeout: 5
                request_delays:
                  kline_fetch: 0.1
                  realtime_fetch: 0.1

            kline:
              daily:
                display_days: 3
                warmup_days: 2
                fetch_days: 5
              weekly:
                display_weeks: 3
                warmup_weeks: 2
                fetch_weeks: 5

            files:
              data_dir: "data"
              outputs_dir: "outputs"
              html_file: "index.html"
              editorial_content_file: "editorial_content.yaml"
              data_files:
                kline: "etf_full_kline_data.json"
                realtime: "etf_realtime_data.json"


            html_update:
              locators:
                report_date_label: "报告日期:"
                data_cutoff_label: "数据截止:"
                generation_time_label: "生成时间:"
                kline_const: "const klineData = "
                realtime_const: "const realtimeData = "
              date_patterns:
                report_date: '\\d{4}年\\d{2}月\\d{2}日'
                iso_date: '\\d{4}-\\d{2}-\\d{2}'
              date_formats:
                report_date_cn: "%Y年%m月%d日"
                iso_date: "%Y-%m-%d"
            """
        ).strip(),
        encoding="utf-8",
    )

    (config_dir / "holdings.yaml").write_text(
        textwrap.dedent(
            """
            holdings:
              "510000":
                total_ratio: 12.5
                components:
                  - code: "600000"
                    name: "示例股份"
                    market: "sh"
                    ratio: 12.5
            """
        ).strip(),
        encoding="utf-8",
    )


    return config_dir


@pytest.fixture
def fake_response_factory():
    class FakeResponse:
        def __init__(self, status_code=200, json_data=None, text=""):
            self.status_code = status_code
            self._json_data = json_data
            self.text = text
            self.encoding = None

        def json(self):
            return self._json_data

    def _factory(status_code=200, json_data=None, text=""):
        return FakeResponse(status_code=status_code, json_data=json_data, text=text)

    return _factory
