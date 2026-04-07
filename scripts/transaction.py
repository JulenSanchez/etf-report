#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
事务管理模块 - 提供备份/恢复/清理机制，确保 HTML 更新失败时可以自动回滚

功能：
1. backup()   - 创建备份快照（data/*.json + outputs/index.html + outputs/js/）
2. restore()  - 从备份恢复文件
3. cleanup()  - 清理过期备份
4. list_backups() - 查看所有备份

用法（在 update_report.py 中集成）：
    tx = TransactionManager(skill_dir)
    backup_path = tx.backup()
    try:
        # ... 执行所有更新步骤 ...
    except Exception as e:
        tx.restore(backup_path)
        raise
    tx.cleanup()
"""

import os
import shutil
from datetime import datetime, timedelta

from logger import Logger
from config_manager import get_config

# 日志初始化
logger = Logger(name="transaction", level="INFO", file_output=True)

# 配置管理器初始化
config = get_config()

# 工作目录
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(WORK_DIR)  # skill根目录


class TransactionManager:
    """事务管理器：备份/恢复/清理"""

    def __init__(self, skill_dir):
        """
        Args:
            skill_dir: 技能根目录路径（包含 data/ 和 outputs/）
        """
        self.skill_dir = skill_dir
        
        # 从配置加载相关参数
        files_config = config.get_files_config()
        transaction_config = config.get_transaction_config()
        data_files_config = files_config.get('data_files', {})
        
        self.data_dir = os.path.join(skill_dir, files_config.get('data_dir', 'data'))
        self.outputs_dir = os.path.join(skill_dir, files_config.get('outputs_dir', 'outputs'))
        
        # 备份目录（从配置加载）
        backup_dir = transaction_config.get('backup_dir', '.backup')
        self.backup_root = os.path.join(skill_dir, backup_dir)
        
        # 最大备份数
        self.max_backups = transaction_config.get('max_backups', 5)
        
        # 需要备份的 data/ 下的 JSON 文件（从配置加载）
        self.data_files = [
            data_files_config.get('kline', 'etf_full_kline_data.json'),
            data_files_config.get('realtime', 'etf_realtime_data.json'),
        ]
        
        # 时间戳格式
        self.timestamp_format = transaction_config.get('timestamp_format', '%Y%m%d_%H%M%S')
        
        # 记录配置加载
        logger.info("事务管理器初始化", {
            "backup_dir": self.backup_root,
            "max_backups": self.max_backups
        })

    def _get_timestamp(self):
        """返回格式化的时间戳"""
        return datetime.now().strftime(self.timestamp_format)

    def backup(self):
        """
        创建备份快照
        备份 data/*.json 文件 + outputs/index.html + outputs/js/（如果存在）
        超过 max_backups 个备份时自动清理最旧的

        Returns:
            str: 备份目录路径，失败返回 None
        """
        ts = self._get_timestamp()
        backup_path = os.path.join(self.backup_root, f"backup_{ts}")

        logger.info("创建备份", {"timestamp": ts})

        try:
            # 备份 data 文件
            data_backup = os.path.join(backup_path, "data")
            for fname in self.data_files:
                src = os.path.join(self.data_dir, fname)
                dst = os.path.join(data_backup, fname)
                if os.path.exists(src):
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)

            # 备份 outputs/index.html
            html_src = os.path.join(self.outputs_dir, "index.html")
            html_dst = os.path.join(backup_path, "outputs", "index.html")
            if os.path.exists(html_src):
                os.makedirs(os.path.dirname(html_dst), exist_ok=True)
                shutil.copy2(html_src, html_dst)

            # 备份 outputs/js/（如果存在）
            js_src = os.path.join(self.outputs_dir, "js")
            js_dst = os.path.join(backup_path, "outputs", "js")
            if os.path.isdir(js_src):
                shutil.copytree(js_src, js_dst)

            logger.info("备份完成", {"path": backup_path})

            # 清理超出数量的旧备份
            self._trim_excess()

            return backup_path

        except Exception as e:
            logger.error("备份失败", {"error": str(e)})
            return None

    def restore(self, backup_path=None):
        """
        从备份恢复文件
        如果未指定 backup_path，使用最新的备份

        Returns:
            bool: 恢复是否成功
        """
        if backup_path is None:
            backup_path = self.get_latest_backup()

        if not backup_path or not os.path.isdir(backup_path):
            logger.error("备份不存在，无法恢复")
            return False

        logger.info("从备份恢复", {"backup": os.path.basename(backup_path)})

        try:
            # 恢复 data 文件
            data_backup = os.path.join(backup_path, "data")
            if os.path.isdir(data_backup):
                for fname in self.data_files:
                    src = os.path.join(data_backup, fname)
                    dst = os.path.join(self.data_dir, fname)
                    if os.path.exists(src):
                        shutil.copy2(src, dst)
                        logger.info("文件恢复成功", {"file": fname})

            # 恢复 outputs/index.html
            html_src = os.path.join(backup_path, "outputs", "index.html")
            html_dst = os.path.join(self.outputs_dir, "index.html")
            if os.path.exists(html_src):
                shutil.copy2(html_src, html_dst)
                logger.info("文件恢复成功", {"file": "index.html"})

            # 恢复 outputs/js/
            js_src = os.path.join(backup_path, "outputs", "js")
            js_dst = os.path.join(self.outputs_dir, "js")
            if os.path.isdir(js_src):
                if os.path.isdir(js_dst):
                    shutil.rmtree(js_dst)
                shutil.copytree(js_src, js_dst)
                logger.info("文件恢复成功", {"file": "js/"})

            logger.info("恢复完成")
            return True

        except Exception as e:
            logger.error("恢复失败", {"error": str(e)})
            return False

    def cleanup(self, max_age_days=5):
        """
        清理过期备份（> max_age_days 天的）

        Returns:
            int: 清理的备份数量
        """
        if not os.path.isdir(self.backup_root):
            return 0

        cutoff = datetime.now() - timedelta(days=max_age_days)
        cleaned = 0

        for name in os.listdir(self.backup_root):
            full = os.path.join(self.backup_root, name)
            if not os.path.isdir(full) or not name.startswith("backup_"):
                continue

            # 从目录名提取时间戳: backup_20260407_114300
            try:
                ts_str = name.replace("backup_", "")
                ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                if ts < cutoff:
                    shutil.rmtree(full)
                    cleaned += 1
                    logger.info("清理旧备份", {"backup": name})
            except ValueError:
                continue

        return cleaned

    def get_latest_backup(self):
        """获取最新备份路径，不存在返回 None"""
        backups = self._get_all_backup_dirs()
        return backups[-1] if backups else None

    def list_backups(self):
        """返回备份列表，按时间倒序"""
        backups = self._get_all_backup_dirs()
        return list(reversed(backups))

    def _get_all_backup_dirs(self):
        """返回所有备份目录路径列表（按名称排序，即按时间正序）"""
        if not os.path.isdir(self.backup_root):
            return []

        dirs = []
        for name in os.listdir(self.backup_root):
            full = os.path.join(self.backup_root, name)
            if os.path.isdir(full) and name.startswith("backup_"):
                dirs.append(full)

        dirs.sort()  # 时间戳格式保证按时间正序
        return dirs

    def _trim_excess(self):
        """保留最新 max_backups 个备份，删除更早的"""
        backups = self._get_all_backup_dirs()
        while len(backups) > self.max_backups:
            old = backups.pop(0)
            shutil.rmtree(old)
            logger.info("清理超额备份", {"backup": os.path.basename(old)})


if __name__ == "__main__":
    # 独立测试
    tx = TransactionManager(SKILL_DIR)

    logger.info("=" * 50)
    logger.info("事务管理器测试")
    logger.info("=" * 50)

    # 1. 创建备份
    path = tx.backup()
    logger.info("备份完成", {"path": path})

    # 2. 列出备份
    logger.info("现有备份列表", {
        "count": len(tx.list_backups()),
        "backups": [os.path.basename(b) for b in tx.list_backups()]
    })

    # 3. 恢复
    logger.info("最新备份", {"path": tx.get_latest_backup()})

    logger.info("测试完成")
