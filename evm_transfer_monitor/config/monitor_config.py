"""
监控配置管理模块

统一管理所有监控相关的配置参数，便于维护和调整
支持两种监控策略：大额交易监控 和 指定地址监控
"""

from dataclasses import dataclass, field
from typing import Dict
from enum import Enum
from config.base_config import ActiveConfig, ConfigMap
from utils.load_address import load_wallet_addresses


class MonitorStrategy(Enum):
    """监控策略枚举"""
    LARGE_AMOUNT = "large_amount"      # 大额交易监控
    WATCH_ADDRESS = "watch_address"    # 指定地址监控


@dataclass
class MonitorConfig:
    """监控配置类 - 集中管理所有配置参数"""
    
    # 基础连接配置
    chain_name: str = ActiveConfig.get("chain_name", "core")  # 链名称
    block_time: int = ActiveConfig.get("block_time", 3)  # 出块时间（秒）
    rpc_url: str = ActiveConfig.get("rpc_url", "")
    scan_url: str = ActiveConfig.get("scan_url", "")
    token_name: str = ActiveConfig.get("token_name", "")
    usdt_contract: str = ActiveConfig.get("usdt_contract", "")
    usdc_contract: str = ActiveConfig.get("usdc_contract", "")
    
    # 监控策略配置 - 默认使用大额交易监控
    monitor_strategy: MonitorStrategy = MonitorStrategy.WATCH_ADDRESS
    
    # 监控参数配置
    required_confirmations: int = ActiveConfig.get("confirmation_blocks", 10)  # 需要的确认数
    confirmation_check_interval: int = 10  # 秒
    cache_ttl: float = 1.5  # 缓存时间
    transaction_timeout: int = 300  # 交易超时时间（秒）
    
    # 大额交易阈值配置（仅在 LARGE_AMOUNT 策略下使用）
    thresholds: Dict[str, float] = field(default_factory=lambda: {
        ActiveConfig.get("token_name", "ETH"): 1.0,
        'USDT': 10000.0,
        'USDC': 10000.0,
    })
    
    # 监控地址列表（仅在 WATCH_ADDRESS 策略下使用）
    watch_addresses: list = field(default_factory=load_wallet_addresses)
    
    # 缓存的小写地址集合，用于快速查找
    _watch_addresses_set: set = field(default_factory=set, init=False)
    
    # API限制配置
    max_rpc_per_second: int = 4
    max_rpc_per_day: int = 90000
    
    # 日志配置
    stats_log_interval: int = 300  # 性能统计日志间隔（秒）

    def __post_init__(self):
        """初始化后处理 - 构建地址查找集合"""
        self._update_watch_addresses_cache()
    
    def _update_watch_addresses_cache(self):
        """更新地址查找缓存"""
        self._watch_addresses_set = {addr.lower() for addr in self.watch_addresses}
    
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
        address_lower = address.lower()
        if address_lower not in self._watch_addresses_set:
            self.watch_addresses.append(address)
            self._watch_addresses_set.add(address_lower)
    
    def remove_watch_address(self, address: str) -> None:
        """移除监控地址"""
        address_lower = address.lower()
        if address_lower in self._watch_addresses_set:
            # 从列表中移除（保持原始大小写）
            self.watch_addresses = [addr for addr in self.watch_addresses 
                                   if addr.lower() != address_lower]
            # 从集合中移除
            self._watch_addresses_set.discard(address_lower)
    
    def is_watched_address(self, address: str) -> bool:
        """检查地址是否在监控列表中 - O(1) 时间复杂度"""
        return address.lower() in self._watch_addresses_set
    
    def update_watch_addresses(self, new_addresses: list) -> None:
        """批量更新监控地址列表"""
        self.watch_addresses = new_addresses.copy()
        self._update_watch_addresses_cache()
    
    def get_watch_addresses_count(self) -> int:
        """获取监控地址数量"""
        return len(self._watch_addresses_set)
    
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
            'watch_addresses_count': len(self._watch_addresses_set),
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
    
    @classmethod
    def from_chain_name(cls, chain_name: str) -> 'MonitorConfig':
        """通过链名称创建监控配置实例
        
        Args:
            chain_name: 链名称，如 'core', 'bsc', 'ethereum' 等
            
        Returns:
            MonitorConfig: 配置实例
            
        Raises:
            ValueError: 当指定的链名称不存在时
        """
        if chain_name not in ConfigMap:
            available_chains = list(ConfigMap.keys())
            raise ValueError(f"链 '{chain_name}' 不存在。可用的链: {available_chains}")
        
        chain_config = ConfigMap[chain_name]
        
        # 创建新的配置实例，使用指定链的配置
        return cls(
            chain_name=chain_name,
            block_time=chain_config.get("block_time", 3),
            rpc_url=chain_config.get("rpc_url", ""),
            scan_url=chain_config.get("scan_url", ""),
            token_name=chain_config.get("token_name", ""),
            usdt_contract=chain_config.get("usdt_contract", ""),
            usdc_contract=chain_config.get("usdc_contract", ""),
            required_confirmations=chain_config.get("confirmation_blocks", 10),
            # 使用指定链的代币名称更新阈值
            thresholds={
                chain_config.get("token_name", "ETH"): 1.0,
                'USDT': 10000.0,
                'USDC': 10000.0,
            }
        )
    
    @staticmethod
    def get_available_chains() -> list:
        """获取所有可用的链名称"""
        return list(ConfigMap.keys())
    
    @staticmethod
    def get_chain_config(chain_name: str) -> Dict:
        """获取指定链的完整配置信息
        
        Args:
            chain_name: 链名称
            
        Returns:
            Dict: 链配置字典
            
        Raises:
            ValueError: 当指定的链名称不存在时
        """
        if chain_name not in ConfigMap:
            available_chains = list(ConfigMap.keys())
            raise ValueError(f"链 '{chain_name}' 不存在。可用的链: {available_chains}")
        
        return ConfigMap[chain_name].copy()
    
    def switch_chain(self, chain_name: str) -> None:
        """切换到指定的链配置
        
        Args:
            chain_name: 目标链名称
            
        Raises:
            ValueError: 当指定的链名称不存在时
        """
        if chain_name not in ConfigMap:
            available_chains = list(ConfigMap.keys())
            raise ValueError(f"链 '{chain_name}' 不存在。可用的链: {available_chains}")
        
        chain_config = ConfigMap[chain_name]
        
        # 更新当前实例的配置
        self.rpc_url = chain_config.get("rpc_url", "")
        self.scan_url = chain_config.get("scan_url", "")
        self.token_name = chain_config.get("token_name", "")
        self.usdt_contract = chain_config.get("usdt_contract", "")
        self.usdc_contract = chain_config.get("usdc_contract", "")
        self.required_confirmations = chain_config.get("confirmation_blocks", 10)
        
        # 更新阈值配置中的主代币名称
        old_token_threshold = self.thresholds.get(self.token_name, 1.0)
        new_token_name = chain_config.get("token_name", "ETH")
        
        # 移除旧的主代币阈值，添加新的
        if self.token_name in self.thresholds:
            del self.thresholds[self.token_name]
        self.thresholds[new_token_name] = old_token_threshold
        
        self.token_name = new_token_name
    
    def get_current_chain_info(self) -> Dict:
        """获取当前配置对应的链信息"""
        for chain_name, chain_config in ConfigMap.items():
            if (chain_config.get("rpc_url") == self.rpc_url and 
                chain_config.get("token_name") == self.token_name):
                return {
                    "chain_name": chain_name,
                    "chain_config": chain_config.copy()
                }
        
        return {
            "chain_name": "unknown",
            "chain_config": {
                "rpc_url": self.rpc_url,
                "token_name": self.token_name,
                "scan_url": self.scan_url
            }
        }
