"""Tuner 端口单一事实源。

所有 Tuner 端口都从这里读取：config/tuner_config.json。
改端口只改那个 JSON 文件，不要在各脚本里硬编码。

PowerShell 侧（StartTuner.ps1）也读同一个 JSON（ConvertFrom-Json），
所以 Python 和 PowerShell 始终指向同一端口。
"""
import json
from pathlib import Path

_PROJECT_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "config").is_dir() and (parent / "scripts").is_dir()
)
_CONFIG_PATH = _PROJECT_ROOT / "config" / "tuner_config.json"

with _CONFIG_PATH.open("r", encoding="utf-8") as _f:
    _cfg = json.load(_f)

DEV_TUNER_PORT = int(_cfg["dev_port"])
PROD_TUNER_PORT = int(_cfg["prod_port"])
