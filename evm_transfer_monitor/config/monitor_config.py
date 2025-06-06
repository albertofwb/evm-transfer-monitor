"""
监控配置管理模块

统一管理所有监控相关的配置参数，便于维护和调整
支持两种监控策略：大额交易监控 和 指定地址监控
"""

from dataclasses import dataclass, field
from typing import Dict
from enum import Enum
from config.base_config import ActiveConfig
from utils.load_address import load_wallet_addresses


class MonitorStrategy(Enum):
    """监控策略枚举"""
    LARGE_AMOUNT = "large_amount"      # 大额交易监控
    WATCH_ADDRESS = "watch_address"    # 指定地址监控


@dataclass
class MonitorConfig:
    """监控配置类 - 集中管理所有配置参数"""
    
    # 基础连接配置
    rpc_url: str = ActiveConfig["rpc_url"]
    scan_url: str = ActiveConfig["scan_url"]
    token_name: str = ActiveConfig["token_name"]
    usdt_contract: str = ActiveConfig["usdt_contract"]
    usdc_contract: str = ActiveConfig["usdc_contract"]
    
    # 监控策略配置 - 默认使用大额交易监控
    monitor_strategy: MonitorStrategy = MonitorStrategy.WATCH_ADDRESS
    
    # 监控参数配置
    required_confirmations: int = 3
    confirmation_check_interval: int = 10  # 秒
    cache_ttl: float = 1.5  # 缓存时间
    transaction_timeout: int = 300  # 交易超时时间（秒）
    
    # 大额交易阈值配置（仅在 LARGE_AMOUNT 策略下使用）
    thresholds: Dict[str, float] = field(default_factory=lambda: {
        ActiveConfig["token_name"]: 1.0,
        'USDT': 10000.0,
        'USDC': 10000.0,
    })
    
    # 监控地址列表（仅在 WATCH_ADDRESS 策略下使用）
    watch_addresses: list = field(default_factory=load_wallet_addresses)
    
    # API限制配置
    max_rpc_per_second: int = 4
    max_rpc_per_day: int = 90000
    
    # 日志配置
    stats_log_interval: int = 300  # 性能统计日志间隔（秒）

    def set_strategy(self, strategy: MonitorStrategy) -> None:
        """设置监控策略"""
        self.monitor_strategy = strategy

    def is_large_amount_strategy(self) -> bool:
        """检查是否为大额交易监控策略"""
        return self.monitor_strategy == MonitorStrategy.LARGE_AMOUNT

    def is_watch_address_strategy(self) -> bool:
        """检查是否为指定地址监控策略"""
        return self.monitor_strategy == MonitorStrategy.WATCH_ADDRESS

    # 大额交易策略相关方法
    def update_thresholds(self, **new_thresholds) -> None:
        """更新交易阈值配置（仅在大额交易策略下有效）"""
        if not self.is_large_amount_strategy():
            raise ValueError("阈值配置仅在大额交易监控策略下有效")
        
        for token, threshold in new_thresholds.items():
            if token in self.thresholds:
                self.thresholds[token] = threshold
            else:
                # 对于新的代币类型，也允许添加
                self.thresholds[token] = threshold
    
    def get_threshold(self, token_type: str) -> float:
        """获取指定代币的阈值（仅在大额交易策略下有效）"""
        if not self.is_large_amount_strategy():
            return 0  # 地址监控策略下不检查阈值
        return self.thresholds.get(token_type, float('inf'))

    # 地址监控策略相关方法
    def add_watch_address(self, address: str) -> None:
        """添加监控地址"""
        if address.lower() not in [addr.lower() for addr in self.watch_addresses]:
            self.watch_addresses.append(address)
    
    def remove_watch_address(self, address: str) -> None:
        """移除监控地址"""
        self.watch_addresses = [addr for addr in self.watch_addresses 
                               if addr.lower() != address.lower()]
    
    def is_watched_address(self, address: str) -> bool:
        """检查地址是否在监控列表中"""
        return address.lower() in [addr.lower() for addr in self.watch_addresses]
    
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
            'monitor_strategy': self.monitor_strategy.value,
            'required_confirmations': self.required_confirmations,
            'confirmation_check_interval': self.confirmation_check_interval,
            'cache_ttl': self.cache_ttl,
            'transaction_timeout': self.transaction_timeout,
            'thresholds': self.thresholds.copy(),
            'watch_addresses': self.watch_addresses.copy(),
            'max_rpc_per_second': self.max_rpc_per_second,
            'max_rpc_per_day': self.max_rpc_per_day,
            'stats_log_interval': self.stats_log_interval,
        }

    def get_strategy_description(self) -> str:
        """获取当前策略的描述"""
        if self.is_large_amount_strategy():
            return f"大额交易监控 - 阈值: {self.thresholds}"
        else:
            return f"指定地址监控 - 监控 {len(self.watch_addresses)} 个地址"
