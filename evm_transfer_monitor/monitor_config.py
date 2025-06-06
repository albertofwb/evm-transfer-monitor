"""
监控配置管理模块

统一管理所有监控相关的配置参数，便于维护和调整
"""

from dataclasses import dataclass, field
from typing import Dict
from config import ActiveConfig


@dataclass
class MonitorConfig:
    """监控配置类 - 集中管理所有配置参数"""
    
    # 基础连接配置
    rpc_url: str = ActiveConfig["rpc_url"]
    scan_url: str = ActiveConfig["scan_url"]
    token_name: str = ActiveConfig["token_name"]
    usdt_contract: str = ActiveConfig["usdt_contract"]
    usdc_contract: str = ActiveConfig["usdc_contract"]
    
    # 监控参数配置
    required_confirmations: int = 3
    confirmation_check_interval: int = 10  # 秒
    cache_ttl: float = 1.5  # 缓存时间
    transaction_timeout: int = 300  # 交易超时时间（秒）
    
    # 交易阈值配置
    thresholds: Dict[str, float] = field(default_factory=lambda: {
        ActiveConfig["token_name"]: 1.0,
        'USDT': 10000.0,
        'USDC': 10000.0,
    })
    
    # API限制配置
    max_rpc_per_second: int = 4
    max_rpc_per_day: int = 90000
    
    # 日志配置
    stats_log_interval: int = 300  # 性能统计日志间隔（秒）
    
    def update_thresholds(self, **new_thresholds) -> None:
        """更新交易阈值配置"""
        for token, threshold in new_thresholds.items():
            if token in self.thresholds:
                self.thresholds[token] = threshold
            else:
                # 对于新的代币类型，也允许添加
                self.thresholds[token] = threshold
    
    def get_threshold(self, token_type: str) -> float:
        """获取指定代币的阈值"""
        return self.thresholds.get(token_type, float('inf'))
    
    def is_within_rate_limits(self, current_rps: float, daily_calls: int) -> bool:
        """检查是否在速率限制范围内"""
        return (current_rps <= self.max_rpc_per_second and 
                daily_calls <= self.max_rpc_per_day)
    
    def to_dict(self) -> Dict:
        """转换为字典格式，便于序列化"""
        return {
            'rpc_url': self.rpc_url,
            'scan_url': self.scan_url,
            'token_name': self.token_name,
            'required_confirmations': self.required_confirmations,
            'confirmation_check_interval': self.confirmation_check_interval,
            'cache_ttl': self.cache_ttl,
            'transaction_timeout': self.transaction_timeout,
            'thresholds': self.thresholds.copy(),
            'max_rpc_per_second': self.max_rpc_per_second,
            'max_rpc_per_day': self.max_rpc_per_day,
            'stats_log_interval': self.stats_log_interval,
        }
