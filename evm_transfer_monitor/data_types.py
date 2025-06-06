"""
监控数据类型定义

定义监控过程中使用的各种数据结构
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class TransactionInfo:
    """交易信息数据类"""
    hash: str
    tx: Dict[str, Any]
    value: float
    tx_type: str
    found_at: float
    block_number: int
    token_info: Optional[Dict[str, Any]] = None
    
    def __str__(self) -> str:
        return (f"TransactionInfo(hash={self.hash[:10]}..., "
                f"type={self.tx_type}, value={self.value}, "
                f"block={self.block_number})")
    
    def is_token_transaction(self) -> bool:
        """判断是否为代币交易"""
        return self.token_info is not None
    
    def get_from_address(self) -> str:
        """获取发送方地址"""
        if self.is_token_transaction() and self.token_info:
            return self.token_info.get('from', '')
        return self.tx.get('from', '')
    
    def get_to_address(self) -> str:
        """获取接收方地址"""
        if self.is_token_transaction() and self.token_info:
            return self.token_info.get('to', '')
        return self.tx.get('to', '')


@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    rpc_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avg_rpc_per_second: float = 0.0
    cache_hit_rate: float = 0.0
    estimated_daily_calls: float = 0.0
    within_rate_limit: bool = True
    api_usage_percent: float = 0.0
    rpc_calls_by_type: Dict[str, int] = None
    
    def __post_init__(self):
        if self.rpc_calls_by_type is None:
            self.rpc_calls_by_type = {}


@dataclass
class TransactionStats:
    """交易统计数据类"""
    transactions_found: Dict[str, int] = None
    token_contracts_detected: int = 0
    token_transactions_processed: int = 0
    token_success_rate: float = 0.0
    
    def __post_init__(self):
        if self.transactions_found is None:
            self.transactions_found = {'total': 0}


@dataclass
class MonitorStatus:
    """监控状态数据类"""
    is_running: bool = False
    blocks_processed: int = 0
    pending_transactions: int = 0
    start_time: float = 0.0
    runtime_hours: float = 0.0
    current_block: int = 0
    last_activity: float = 0.0
    
    def update_runtime(self, current_time: float) -> None:
        """更新运行时间"""
        if self.start_time > 0:
            self.runtime_hours = (current_time - self.start_time) / 3600
