#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理器 - 统一管理YAML配置

提供：
1. 单例模式的ConfigManager
2. 配置热更新支持
3. 配置校验
4. 默认值回退
"""

import yaml
import os
from typing import Any, Dict, List, Optional
from pathlib import Path


class ConfigManager:
    """配置管理器 - 单例模式"""
    
    _instance = None
    _config = None
    _config_dir = None
    _loaded = False
    
    def __new__(cls, config_dir=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config_dir=None):
        if config_dir and config_dir != self._config_dir:
            self._config_dir = config_dir
            self._load_config()
        elif not self._loaded:
            self._load_config()
    
    def _get_config_path(self, filename):
        """获取配置文件完整路径"""
        if self._config_dir is None:
            # 默认: scripts目录的上级/config
            script_dir = os.path.dirname(os.path.abspath(__file__))
            skill_dir = os.path.dirname(script_dir)
            self._config_dir = os.path.join(skill_dir, "config")
        
        return os.path.join(self._config_dir, filename)
    
    def _load_config(self):
        """加载配置文件"""
        try:
            config_path = self._get_config_path("config.yaml")
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f)
            
            if self._config is None:
                self._config = {}
            
            # 加载成分股配置
            holdings_path = self._get_config_path("holdings.yaml")
            if os.path.exists(holdings_path):
                with open(holdings_path, 'r', encoding='utf-8') as f:
                    holdings = yaml.safe_load(f)
                    if holdings and 'holdings' in holdings:
                        self._config['holdings'] = holdings['holdings']
            
            print(f"[OK] 配置已加载: {config_path}")
            self._loaded = True
        except Exception as e:
            print(f"[ERROR] 配置加载失败: {e}")
            self._config = {}
            self._loaded = True
    
    def reload(self):
        """重新加载配置"""
        self._loaded = False
        self._load_config()
    
    def get_etfs(self) -> List[Dict]:
        """获取ETF列表"""
        return self._config.get('etfs', [])
    
    def get_etf_codes(self) -> List[str]:
        """获取ETF代码列表"""
        return [etf['code'] for etf in self.get_etfs()]
    
    def get_holdings(self, etf_code: str) -> Dict:
        """获取特定ETF的成分股"""
        holdings = self._config.get('holdings', {})
        return holdings.get(etf_code, {})
    
    def get_api_config(self) -> Dict:
        """获取API配置"""
        return self._config.get('api', {})
    
    def get_kline_config(self) -> Dict:
        """获取K线配置"""
        return self._config.get('kline', {})
    
    def get_files_config(self) -> Dict:
        """获取文件路径配置"""
        return self._config.get('files', {})
    
    def get_system_check_config(self) -> Dict:
        """获取系统检查配置"""
        return self._config.get('system_check', {})
    
    def get_html_update_config(self) -> Dict:
        """获取HTML更新配置"""
        return self._config.get('html_update', {})
    
    def get_transaction_config(self) -> Dict:
        """获取事务管理配置"""
        return self._config.get('transaction', {})
    
    def get(self, key: str, default: Any = None) -> Any:
        """通用配置获取（支持点号分隔）
        
        例子:
            config.get('api.sina.timeout') -> 10
            config.get('kline.daily.display_days') -> 60
        """
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        
        return value if value is not None else default
    
    def validate(self) -> bool:
        """验证配置完整性"""
        try:
            # 检查ETF数量
            etfs = self.get_etfs()
            if len(etfs) == 0:
                print("[WARN] ETF列表为空")
                return False
            
            # 检查必需字段
            for etf in etfs:
                if 'code' not in etf:
                    print(f"[ERROR] ETF缺少code字段: {etf}")
                    return False
                if 'name' not in etf:
                    print(f"[ERROR] ETF缺少name字段: {etf}")
                    return False
            
            # 检查API配置
            api_config = self.get_api_config()
            if not api_config:
                print("[WARN] API配置缺失")
                return False
            
            # 检查文件配置
            files_config = self.get_files_config()
            if not files_config:
                print("[WARN] 文件配置缺失")
                return False
            
            print("[OK] 配置验证通过")
            return True
        except Exception as e:
            print(f"[ERROR] 配置验证失败: {e}")
            return False


# 全局单例
_config_manager = None


def get_config(config_dir=None) -> ConfigManager:
    """获取配置管理器单例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_dir)
    return _config_manager


if __name__ == "__main__":
    # 测试配置加载
    config = get_config()
    
    print("\n[TEST] 配置管理器测试")
    print("-" * 40)
    
    # 测试ETF列表
    etfs = config.get_etfs()
    print(f"ETF数量: {len(etfs)}")
    print(f"ETF代码: {config.get_etf_codes()}")
    
    # 测试点号分隔查询
    display_days = config.get('kline.daily.display_days')
    print(f"K线显示天数: {display_days}")
    
    timeout = config.get('api.sina.timeout')
    print(f"API超时时间: {timeout}")
    
    # 测试成分股查询
    holdings_512400 = config.get_holdings("512400")
    if holdings_512400:
        print(f"512400成分股数量: {len(holdings_512400.get('components', []))}")
    
    # 验证配置
    config.validate()
