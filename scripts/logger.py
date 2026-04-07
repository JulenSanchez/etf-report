#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结构化日志系统 - 支持 JSON 格式输出、多级别日志、时间戳和文件持久化

功能：
1. 支持 DEBUG/INFO/WARN/ERROR 四个日志级别
2. JSON 格式输出（易于 AI 解析和分析）
3. 可选文件输出（logs/ 目录）
4. 控制台输出（带颜色区分）
5. 时间戳和上下文信息

使用方法：
    from logger import Logger
    
    logger = Logger(name="update_report", file_output=True)
    logger.info("开始更新", {"step": 1, "file": "kline_data.json"})
    logger.error("更新失败", {"reason": "网络超时", "retry": 3})
"""

import os
import json
import sys
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path


class Logger:
    """结构化日志记录器"""
    
    # 日志级别定义
    LEVELS = {
        "DEBUG": 0,
        "INFO": 1,
        "WARN": 2,
        "ERROR": 3,
    }
    
    # 控制台颜色定义（ANSI）
    COLORS = {
        "DEBUG": "\033[36m",    # 青色
        "INFO": "\033[32m",     # 绿色
        "WARN": "\033[33m",     # 黄色
        "ERROR": "\033[31m",    # 红色
        "RESET": "\033[0m",
    }
    
    def __init__(
        self,
        name: str = "logger",
        level: str = "INFO",
        file_output: bool = False,
        log_dir: Optional[str] = None,
        enable_console: bool = True,
    ):
        """
        初始化日志记录器
        
        Args:
            name: 日志记录器名称（用于日志文件和上下文）
            level: 最低日志级别（DEBUG/INFO/WARN/ERROR）
            file_output: 是否输出到文件
            log_dir: 日志文件目录，默认为 logs/
            enable_console: 是否输出到控制台
        """
        self.name = name
        self.level = level.upper()
        self.enable_console = enable_console
        self.file_output = file_output
        
        if self.level not in self.LEVELS:
            raise ValueError(f"Invalid log level: {level}")
        
        # 初始化文件输出
        if self.file_output:
            if log_dir is None:
                # 默认日志目录：脚本所在目录的 logs/ 下
                script_dir = os.path.dirname(os.path.abspath(__file__))
                skill_dir = os.path.dirname(script_dir)
                log_dir = os.path.join(skill_dir, "logs")
            
            self.log_dir = log_dir
            os.makedirs(self.log_dir, exist_ok=True)
            
            # 日志文件路径：logs/logger_name_YYYYMMDD.jsonl
            today = datetime.now().strftime("%Y%m%d")
            self.log_file = os.path.join(self.log_dir, f"{name}_{today}.jsonl")
        else:
            self.log_dir = None
            self.log_file = None
    
    def _should_log(self, level: str) -> bool:
        """检查是否应该记录该级别的日志"""
        return self.LEVELS.get(level, 4) >= self.LEVELS.get(self.level, 1)
    
    def _format_record(
        self,
        level: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """格式化日志记录"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "logger": self.name,
            "level": level,
            "message": message,
        }
        
        if context:
            record["context"] = context
        
        return record
    
    def _write_to_file(self, record: Dict[str, Any]) -> None:
        """将日志记录写入文件（JSONL 格式）"""
        if not self.file_output or not self.log_file:
            return
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            # 文件写入失败时，至少在控制台输出错误
            if self.enable_console:
                print(f"[WARNING] 无法写入日志文件: {e}", file=sys.stderr)
    
    def _write_to_console(self, record: Dict[str, Any]) -> None:
        """将日志记录输出到控制台"""
        if not self.enable_console:
            return
        
        level = record["level"]
        color = self.COLORS.get(level, "")
        reset = self.COLORS["RESET"]
        
        # 时间戳
        ts = record["timestamp"]
        
        # 基础消息
        output = f"{color}[{ts}] {level} - {record['message']}{reset}"
        
        # 如果有上下文，以结构化格式追加
        if "context" in record and record["context"]:
            context_json = json.dumps(record["context"], ensure_ascii=False, indent=2)
            output += f"\n  Context:\n"
            for line in context_json.split("\n"):
                output += f"    {line}\n"
        
        print(output, file=sys.stdout if level != "ERROR" else sys.stderr)
    
    def _log(
        self,
        level: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """内部日志记录方法"""
        if not self._should_log(level):
            return
        
        record = self._format_record(level, message, context)
        
        # 写入文件
        if self.file_output:
            self._write_to_file(record)
        
        # 输出到控制台
        self._write_to_console(record)
    
    def debug(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """记录 DEBUG 级别日志"""
        self._log("DEBUG", message, context)
    
    def info(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """记录 INFO 级别日志"""
        self._log("INFO", message, context)
    
    def warn(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """记录 WARN 级别日志"""
        self._log("WARN", message, context)
    
    def error(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """记录 ERROR 级别日志"""
        self._log("ERROR", message, context)
    
    def get_log_file_path(self) -> Optional[str]:
        """获取当前日志文件路径"""
        return self.log_file


# ============================================================
# 全局 logger 单例（方便快速使用）
# ============================================================

_default_logger = None


def get_logger(
    name: str = "etf-report",
    level: str = "INFO",
    file_output: bool = False,
) -> Logger:
    """获取或创建默认日志记录器"""
    global _default_logger
    
    if _default_logger is None:
        _default_logger = Logger(name=name, level=level, file_output=file_output)
    
    return _default_logger


if __name__ == "__main__":
    # 测试脚本
    print("=" * 60)
    print("日志系统测试")
    print("=" * 60)
    
    # 创建测试 logger（启用文件输出）
    test_logger = Logger(name="test", level="DEBUG", file_output=True)
    
    # 测试各个级别
    test_logger.debug("这是一条 DEBUG 消息", {"module": "test", "action": "init"})
    test_logger.info("这是一条 INFO 消息", {"step": 1, "status": "success"})
    test_logger.warn("这是一条 WARN 消息", {"warning": "数据不完整", "items": 5})
    test_logger.error("这是一条 ERROR 消息", {"error": "网络超时", "retry_count": 3})
    
    print(f"\n日志文件已保存到: {test_logger.get_log_file_path()}")
