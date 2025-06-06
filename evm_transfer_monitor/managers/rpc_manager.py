"""
RPC调用管理器

负责Web3连接管理、缓存控制和API调用限制
"""

import asyncio
import time
from collections import defaultdict
from typing import Dict, Any, Optional

from web3 import AsyncWeb3
from web3.middleware import ExtraDataToPOAMiddleware

from config.monitor_config import MonitorConfig
from models.data_types import PerformanceMetrics
from utils.log_utils import get_logger

logger = get_logger(__name__)


class RPCManager:
    """RPC调用管理器 - 负责缓存和限制控制"""
    
    def __init__(self, config: MonitorConfig):
        self.config = config
        self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(config.rpc_url))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        
        # 缓存相关
        self.cached_block_number: Optional[int] = None
        self.cache_time: float = 0
        
        # 统计相关
        self.rpc_calls: int = 0
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.rpc_calls_by_type: Dict[str, int] = defaultdict(int)
        self.start_time: float = time.time()
    
    def log_rpc_call(self, call_type: str = 'other') -> None:
        """记录RPC调用统计"""
        self.rpc_calls += 1
        self.rpc_calls_by_type[call_type] += 1
    
    async def get_cached_block_number(self) -> int:
        """获取缓存的区块号"""
        current_time = time.time()
        
        if (self.cached_block_number is None or 
            current_time - self.cache_time > self.config.cache_ttl):
            self.cached_block_number = await self.w3.eth.get_block_number()
            self.cache_time = current_time
            self.log_rpc_call('get_block_number')
            self.cache_misses += 1
        else:
            self.cache_hits += 1
            
        return self.cached_block_number
    
    async def get_block(self, block_number: int):
        """获取区块信息"""
        self.log_rpc_call('get_block')
        return await self.w3.eth.get_block(block_number, full_transactions=True)
    
    async def get_gas_price(self):
        """获取当前Gas价格"""
        self.log_rpc_call('get_gas_price')
        return await self.w3.eth.gas_price
    
    async def check_rate_limit(self) -> None:
        """检查并执行速率限制"""
        runtime = time.time() - self.start_time
        if runtime <= 0:
            return
            
        avg_rpc_per_second = self.rpc_calls / runtime
        
        if avg_rpc_per_second > self.config.max_rpc_per_second * 0.8:
            delay = 1.0 / self.config.max_rpc_per_second
            logger.warning(f"⚠️ RPC调用频率过高 ({avg_rpc_per_second:.2f}/s)，添加 {delay:.2f}s 延迟")
            await asyncio.sleep(delay)
    
    def get_performance_stats(self) -> PerformanceMetrics:
        """获取性能统计信息"""
        runtime = time.time() - self.start_time
        avg_rpc_per_second = self.rpc_calls / runtime if runtime > 0 else 0
        
        total_requests = self.cache_hits + self.cache_misses
        cache_hit_rate = (self.cache_hits / total_requests) if total_requests > 0 else 0
        
        return PerformanceMetrics(
            rpc_calls=self.rpc_calls,
            cache_hits=self.cache_hits,
            cache_misses=self.cache_misses,
            avg_rpc_per_second=avg_rpc_per_second,
            cache_hit_rate=cache_hit_rate * 100,
            estimated_daily_calls=avg_rpc_per_second * 86400,
            within_rate_limit=avg_rpc_per_second <= self.config.max_rpc_per_second,
            api_usage_percent=(self.rpc_calls / self.config.max_rpc_per_day) * 100,
            rpc_calls_by_type=dict(self.rpc_calls_by_type)
        )
    
    async def test_connection(self) -> Dict[str, Any]:
        """测试网络连接并返回基本信息"""
        logger.info(f"正在测试RPC {self.config.rpc_url} 连接...")
        try:
            latest_block = await self.get_cached_block_number()
            gas_price = await self.get_gas_price()
            gas_price_gwei = self.w3.from_wei(gas_price, 'gwei')
            
            return {
                'success': True,
                'latest_block': latest_block,
                'gas_price_gwei': float(gas_price_gwei),
                'network': self.config.chain_name,
                'rpc_url': self.config.rpc_url
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'rpc_url': self.config.rpc_url
            }
    
    def reset_stats(self) -> None:
        """重置统计数据"""
        self.rpc_calls = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.rpc_calls_by_type.clear()
        self.start_time = time.time()
        logger.info("RPC统计数据已重置")
    
    def is_healthy(self) -> bool:
        """检查RPC管理器健康状态"""
        stats = self.get_performance_stats()
        return (stats.within_rate_limit and 
                stats.api_usage_percent < 90.0 and
                self.cached_block_number is not None)
