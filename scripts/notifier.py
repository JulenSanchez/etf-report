#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企微 Webhook 通知推送

Step 7 of --publish mode:
读取实时行情数据，生成摘要文本，推送到企业微信群。
"""

import json
import os
import yaml
import requests
from datetime import datetime
from typing import Dict, Optional

from logger import Logger
from config_manager import get_config

logger = Logger(name="notifier", level="INFO", file_output=True)


def load_realtime_data(data_dir: str) -> Dict:
    """加载实时行情数据"""
    filepath = os.path.join(data_dir, "etf_realtime_data.json")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def build_summary_text(realtime_data: Dict) -> str:
    """构建企微消息摘要文本（匹配历史推送格式）

    Args:
        realtime_data: etf_realtime_data.json 的内容

    Returns:
        Markdown 格式的摘要文本
    """
    today = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%H:%M:%S")

    # 汇总行情
    etf_items = []
    for code, info in realtime_data.items():
        name = info.get("name", code)
        change = info.get("etf_change", 0)
        etf_items.append((code, name, change))

    # 排序：按涨跌幅降序
    etf_items.sort(key=lambda x: x[2], reverse=True)

    # 找最强/最弱
    strongest = max(etf_items, key=lambda x: x[2])
    weakest = min(etf_items, key=lambda x: x[2])

    lines = [
        f"**ETF投资日报 - {today}**",
        f"更新时间: {time_str}",
        "",
        "## 今日行情一览",
        "",
    ]

    for code, name, change in etf_items:
        if change >= 0:
            bullet = "🔴"
            sign = "+"
        else:
            bullet = "🟢"
            sign = ""
        lines.append(f"**{name}**({code}): {bullet} {sign}{change:.2f}%")

    lines.extend([
        "",
        "## 今日亮点",
        "",
    ])

    # 最强
    _, s_name, s_change = strongest
    if s_change >= 0:
        s_bullet, s_sign = "🔴", "+"
    else:
        s_bullet, s_sign = "🟢", ""
    lines.append(f"**最强**: {s_name} {s_bullet} {s_sign}{s_change:.2f}%")

    # 最弱
    _, w_name, w_change = weakest
    if w_change >= 0:
        w_bullet, w_sign = "🔴", "+"
    else:
        w_bullet, w_sign = "🟢", ""
    lines.append(f"**最弱**: {w_name} {w_bullet} {w_sign}{w_change:.2f}%")

    # 报告链接
    lines.extend([
        "",
        "## 查看完整报告",
        "",
        "[📊 点击打开报告](https://julensanchez.github.io/etf-report/)",
        "---",
        "数据来源: 新浪财经 | 自动推送 by CodeBuddy",
    ])

    return "\n".join(lines)


def send_wecom_webhook(webhook_url: str, content: str, mention_all: bool = False) -> bool:
    """发送企微 Webhook 消息

    Args:
        webhook_url: 企微机器人 Webhook URL
        content: Markdown 格式的消息内容
        mention_all: 是否 @所有人

    Returns:
        是否发送成功
    """
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": content,
        },
    }

    if mention_all:
        payload["markdown"]["mentioned_list"] = ["@all"]

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        result = resp.json()
        if result.get("errcode") == 0:
            logger.info("企微通知发送成功")
            return True
        else:
            logger.error("企微通知发送失败", {"error": result.get("errmsg", "unknown")})
            return False
    except requests.Timeout:
        logger.error("企微通知发送超时")
        return False
    except Exception as e:
        logger.error("企微通知发送异常", {"error": str(e)})
        return False


def main(data_dir: str) -> bool:
    """执行企微通知推送

    Args:
        data_dir: data 目录的绝对路径

    Returns:
        True 表示成功（或被跳过），False 表示失败
    """
    logger.info("=" * 60)
    logger.info("Step 7: 发送企微通知")
    logger.info("=" * 60)

    config = get_config()
    publish_config = config._config.get("publish", {})
    wecom_config = publish_config.get("wecom", {})

    SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if not wecom_config.get("enabled", False):
        logger.info("企微通知未启用，跳过")
        return True

    webhook_url = wecom_config.get("webhook_url", "")
    if not webhook_url:
        # 尝试从 secrets.yaml 读取（不会被提交到 git）
        secrets_path = os.path.join(SKILL_DIR, "config", "secrets.yaml")
        if os.path.exists(secrets_path):
            with open(secrets_path, "r", encoding="utf-8") as f:
                secrets = yaml.safe_load(f) or {}
            webhook_url = (secrets.get("publish", {})
                                  .get("wecom", {})
                                  .get("webhook_url", ""))
    if not webhook_url:
        logger.warn("企微 Webhook URL 未配置，跳过通知")
        return True

    mention_all = wecom_config.get("mention_all", False)

    # 1. 加载实时数据
    try:
        realtime_data = load_realtime_data(data_dir)
    except Exception as e:
        logger.error("无法加载实时行情数据", {"error": str(e)})
        return False

    # 2. 构建摘要
    summary = build_summary_text(realtime_data)
    logger.info("摘要文本已生成", {"length": len(summary)})

    # 3. 发送
    return send_wecom_webhook(webhook_url, summary, mention_all)


if __name__ == "__main__":
    import sys
    SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.path.join(SKILL_DIR, "data")
    success = main(DATA_DIR)
    sys.exit(0 if success else 1)
