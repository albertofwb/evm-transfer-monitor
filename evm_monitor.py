"""
EVM区块链交易监控器 - 重构版本

主要改进：
1. 分离关注点：将不同功能拆分为独立的类
2. 配置管理：统一管理所有配置参数
3. 性能监控：独立的性能统计模块
4. 交易处理：简化交易处理逻辑
5. 错误处理：更好的异常处理和恢复机制
"""

import asyncio
import signal
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from web3 import AsyncWeb3
from web3.exceptions import BlockNotFound, TransactionNotFound
from web3.middleware import ExtraDataToPOAMiddleware

from log_utils import get_logger
from config import ActiveConfig
from token_parser import TokenParser

logger = get_logger(__name__)


@dataclass
class MonitorConfig:
    """监控配置类 - 集中管理所有配置参数"""
    rpc_url: str = ActiveConfig["rpc_url"]
    scan_url: str = ActiveConfig["scan_url"]
    required_confirmations: int = 3
    confirmation_check_interval: int = 10  # 秒
    cache_ttl: float = 1.5  # 缓存时间
    transaction_timeout: int = 300  # 交易超时时间（秒）
    
    # 交易阈值配置
    thresholds: Dict[str, float] = field(default_factory=lambda: {
        'BNB': 1.0,
        'USDT': 10000.0,
        'USDC': 10000.0,
        'BUSD': 10000.0
    })
    
    # API限制配置
    max_rpc_per_second: int = 4
    max_rpc_per_day: int = 90000
    
    # 日志配置
    stats_log_interval: int = 300  # 性能统计日志间隔（秒）


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
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        runtime = time.time() - self.start_time
        avg_rpc_per_second = self.rpc_calls / runtime if runtime > 0 else 0
        
        total_requests = self.cache_hits + self.cache_misses
        cache_hit_rate = (self.cache_hits / total_requests) if total_requests > 0 else 0
        
        return {
            'rpc_calls': self.rpc_calls,
            'avg_rpc_per_second': avg_rpc_per_second,
            'estimated_daily_calls': avg_rpc_per_second * 86400,
            'cache_hit_rate': cache_hit_rate * 100,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'rpc_calls_by_type': dict(self.rpc_calls_by_type),
            'within_rate_limit': avg_rpc_per_second <= self.config.max_rpc_per_second,
            'api_usage_percent': (self.rpc_calls / self.config.max_rpc_per_day) * 100
        }


class TransactionProcessor:
    """交易处理器 - 负责检测和分析交易"""
    
    def __init__(self, config: MonitorConfig, rpc_manager: RPCManager):
        self.config = config
        self.rpc_manager = rpc_manager
        
        # 统计信息
        self.transactions_found: Dict[str, int] = defaultdict(int)
        self.token_contracts_detected: int = 0
        self.token_transactions_processed: int = 0
    
    async def process_transaction(self, tx: Dict[str, Any]) -> Optional[TransactionInfo]:
        """处理单个交易，检测大额转账"""
        block_number = tx.get('blockNumber')
        
        # 检测BNB转账
        bnb_info = self._process_bnb_transaction(tx, block_number)
        if bnb_info:
            return bnb_info
        
        # 检测代币转账
        token_info = self._process_token_transaction(tx, block_number)
        if token_info:
            return token_info
        
        return None
    
    def _process_bnb_transaction(self, tx: Dict[str, Any], block_number: int) -> Optional[TransactionInfo]:
        """处理BNB交易"""
        wei = tx['value']
        bnb_amount = self.rpc_manager.w3.from_wei(wei, 'ether')
        
        if bnb_amount >= self.config.thresholds['BNB']:
            gas_cost = self.rpc_manager.w3.from_wei(tx['gasPrice'] * tx['gas'], 'ether')
            tx_hash = self.rpc_manager.w3.to_hex(tx['hash'])
            
            logger.info(
                f"💰 大额BNB: {tx['from']} => {tx['to']} | "
                f"{TokenParser.format_amount(bnb_amount, 'BNB')} | "
                f"Gas: {gas_cost:,.5f} BNB | "
                f"区块: {block_number} | {self.config.scan_url}/tx/{tx_hash}"
            )
            
            self.transactions_found['BNB'] += 1
            self.transactions_found['total'] += 1
            
            return TransactionInfo(
                hash=tx_hash,
                tx=tx,
                value=bnb_amount,
                tx_type='BNB',
                found_at=time.time(),
                block_number=block_number
            )
        
        return None
    
    def _process_token_transaction(self, tx: Dict[str, Any], block_number: int) -> Optional[TransactionInfo]:
        """处理代币交易"""
        if not tx.get('to'):
            return None
        
        # 检查是否为支持的代币合约
        token_symbol = TokenParser.is_token_contract(tx['to'])
        if not token_symbol:
            return None
        
        self.token_contracts_detected += 1
        
        # 解析代币转账
        token_info = TokenParser.parse_erc20_transfer(tx, token_symbol)
        if not token_info:
            return None
        
        self.token_transactions_processed += 1
        
        # 检查是否为大额转账
        if token_info['amount'] >= self.config.thresholds.get(token_symbol, float('inf')):
            tx_hash = self.rpc_manager.w3.to_hex(tx['hash'])
            
            # 根据代币类型选择图标
            icons = {'USDT': '💵', 'USDC': '💸', 'BUSD': '💴'}
            icon = icons.get(token_symbol, '🪙')
            
            logger.info(
                f"{icon} 大额{token_symbol}: {token_info['from']} => {token_info['to']} | "
                f"{TokenParser.format_amount(token_info['amount'], token_symbol)} | "
                f"区块: {block_number} | {self.config.scan_url}/tx/{tx_hash}"
            )
            
            self.transactions_found[token_symbol] += 1
            self.transactions_found['total'] += 1
            
            return TransactionInfo(
                hash=tx_hash,
                tx=tx,
                value=token_info['amount'],
                tx_type=token_symbol,
                found_at=time.time(),
                block_number=block_number,
                token_info=token_info
            )
        
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取处理统计信息"""
        success_rate = 0
        if self.token_contracts_detected > 0:
            success_rate = (self.token_transactions_processed / self.token_contracts_detected) * 100
        
        return {
            'transactions_found': dict(self.transactions_found),
            'token_contracts_detected': self.token_contracts_detected,
            'token_transactions_processed': self.token_transactions_processed,
            'token_success_rate': success_rate
        }


class ConfirmationManager:
    """确认管理器 - 负责跟踪交易确认状态"""
    
    def __init__(self, config: MonitorConfig, rpc_manager: RPCManager):
        self.config = config
        self.rpc_manager = rpc_manager
        self.pending_by_block: Dict[int, List[TransactionInfo]] = defaultdict(list)
        self.last_check_time: float = 0
    
    def add_pending_transaction(self, tx_info: TransactionInfo) -> None:
        """添加待确认交易"""
        if tx_info.block_number:
            self.pending_by_block[tx_info.block_number].append(tx_info)
    
    async def check_confirmations(self) -> None:
        """检查交易确认状态"""
        current_time = time.time()
        if current_time - self.last_check_time < self.config.confirmation_check_interval:
            return
        
        if not self.pending_by_block:
            return
        
        try:
            current_block = await self.rpc_manager.get_cached_block_number()
            await self.rpc_manager.check_rate_limit()
        except Exception as e:
            logger.error(f"获取当前区块失败: {e}")
            return
        
        blocks_to_remove = []
        confirmed_count = 0
        
        for block_number, tx_list in self.pending_by_block.items():
            confirmations = current_block - block_number + 1
            
            if confirmations >= self.config.required_confirmations:
                for tx_info in tx_list:
                    self._log_confirmed_transaction(tx_info, confirmations)
                    confirmed_count += 1
                blocks_to_remove.append(block_number)
            elif confirmations <= 0:
                logger.warning(f"⚠️ 可能的区块重组，区块 {block_number} 确认数: {confirmations}")
        
        # 清理已确认的区块
        for block_number in blocks_to_remove:
            del self.pending_by_block[block_number]
        
        if confirmed_count > 0:
            logger.debug(f"本轮确认了 {confirmed_count} 个交易")
        
        self.last_check_time = current_time
    
    def _log_confirmed_transaction(self, tx_info: TransactionInfo, confirmations: int) -> None:
        """记录已确认的交易"""
        if tx_info.tx_type == 'BNB':
            logger.info(
                f"✅ BNB交易确认: {tx_info.tx['from']} => {tx_info.tx['to']} | "
                f"{TokenParser.format_amount(tx_info.value, 'BNB')} | "
                f"确认数: {confirmations} | {self.config.scan_url}/tx/{tx_info.hash}"
            )
        else:
            token_info = tx_info.token_info or {}
            logger.info(
                f"✅ {tx_info.tx_type}交易确认: {token_info.get('from', 'N/A')} => {token_info.get('to', 'N/A')} | "
                f"{TokenParser.format_amount(tx_info.value, tx_info.tx_type)} | "
                f"确认数: {confirmations} | {self.config.scan_url}/tx/{tx_info.hash}"
            )
    
    def cleanup_timeout_transactions(self) -> int:
        """清理超时的交易"""
        current_time = time.time()
        timeout_count = 0
        blocks_to_remove = []
        
        for block_number, tx_list in self.pending_by_block.items():
            remaining_txs = []
            for tx_info in tx_list:
                if current_time - tx_info.found_at < self.config.transaction_timeout:
                    remaining_txs.append(tx_info)
                else:
                    timeout_count += 1
                    logger.warning(f"⏰ {tx_info.tx_type}交易确认超时: {tx_info.hash}")
            
            if remaining_txs:
                self.pending_by_block[block_number] = remaining_txs
            else:
                blocks_to_remove.append(block_number)
        
        for block_number in blocks_to_remove:
            del self.pending_by_block[block_number]
        
        return timeout_count
    
    def get_pending_count(self) -> int:
        """获取待确认交易数量"""
        return sum(len(txs) for txs in self.pending_by_block.values())
    
    def get_pending_by_type(self) -> Dict[str, int]:
        """按类型统计待确认交易"""
        pending_by_type = defaultdict(int)
        for tx_list in self.pending_by_block.values():
            for tx_info in tx_list:
                pending_by_type[tx_info.tx_type] += 1
        return dict(pending_by_type)


class StatisticsReporter:
    """统计报告器 - 负责性能统计和日志输出"""
    
    def __init__(self, config: MonitorConfig):
        self.config = config
        self.blocks_processed: int = 0
        self.start_time: float = time.time()
        self.last_stats_log: float = time.time()
    
    def increment_blocks_processed(self) -> None:
        """增加已处理区块数"""
        self.blocks_processed += 1
    
    def should_log_stats(self) -> bool:
        """检查是否应该输出统计日志"""
        current_time = time.time()
        return current_time - self.last_stats_log >= self.config.stats_log_interval
    
    def log_performance_stats(self, rpc_manager: RPCManager, 
                            tx_processor: TransactionProcessor, 
                            confirmation_manager: ConfirmationManager) -> None:
        """输出详细的性能统计"""
        current_time = time.time()
        runtime = current_time - self.start_time
        
        rpc_stats = rpc_manager.get_performance_stats()
        tx_stats = tx_processor.get_stats()
        pending_count = confirmation_manager.get_pending_count()
        pending_by_type = confirmation_manager.get_pending_by_type()
        
        # 基本运行统计
        logger.info(
            f"📊 性能统计 | "
            f"运行: {runtime/3600:.1f}h | "
            f"区块: {self.blocks_processed} | "
            f"交易: {tx_stats['transactions_found']['total']} | "
            f"待确认: {pending_count}"
        )
        
        # 交易类型统计
        self._log_transaction_breakdown(tx_stats['transactions_found'], pending_by_type)
        
        # 代币处理统计
        if tx_stats['token_contracts_detected'] > 0:
            logger.info(
                f"🪙 代币统计 | "
                f"合约调用: {tx_stats['token_contracts_detected']} | "
                f"成功解析: {tx_stats['token_transactions_processed']} | "
                f"解析率: {tx_stats['token_success_rate']:.1f}%"
            )
        
        # RPC统计
        self._log_rpc_stats(rpc_stats)
        
        self.last_stats_log = current_time
    
    def _log_transaction_breakdown(self, found: Dict[str, int], pending: Dict[str, int]) -> None:
        """记录交易分类统计"""
        tx_breakdown = []
        for tx_type, count in found.items():
            if tx_type != 'total' and count > 0:
                pending_count = pending.get(tx_type, 0)
                tx_breakdown.append(f"{tx_type}: {count}({pending_count})")
        
        if tx_breakdown:
            logger.info(f"💰 交易分类 | {' | '.join(tx_breakdown)} | (发现数(待确认数))")
    
    def _log_rpc_stats(self, rpc_stats: Dict[str, Any]) -> None:
        """记录RPC统计信息"""
        rpc_breakdown = " | ".join([
            f"{k}: {v}" for k, v in rpc_stats['rpc_calls_by_type'].items() if v > 0
        ])
        
        logger.info(
            f"🔗 RPC统计 | "
            f"总计: {rpc_stats['rpc_calls']} | "
            f"速率: {rpc_stats['avg_rpc_per_second']:.2f}/s | "
            f"预估日用: {rpc_stats['estimated_daily_calls']:.0f} | "
            f"缓存命中率: {rpc_stats['cache_hit_rate']:.1f}%"
        )
        
        logger.info(f"📈 RPC分类 | {rpc_breakdown}")
        
        # API限制状态
        if rpc_stats['estimated_daily_calls'] > self.config.max_rpc_per_day:
            logger.warning("⚠️ 预估日用量超限！当前速度可能耗尽配额")
        elif not rpc_stats['within_rate_limit']:
            logger.warning(f"⚠️ RPC调用频率超限！建议降低到 {self.config.max_rpc_per_second}/s 以下")
        else:
            logger.info("✅ RPC使用率正常，缓存有效降低了调用频率")
    
    def log_final_stats(self, rpc_manager: RPCManager, 
                       tx_processor: TransactionProcessor, 
                       confirmation_manager: ConfirmationManager) -> None:
        """输出最终统计报告"""
        runtime = time.time() - self.start_time
        rpc_stats = rpc_manager.get_performance_stats()
        tx_stats = tx_processor.get_stats()
        
        logger.info("=" * 80)
        logger.info("📈 最终运行统计报告")
        logger.info(f"🕒 运行时长: {runtime/3600:.2f} 小时")
        logger.info(f"📦 处理区块: {self.blocks_processed} 个")
        
        # 交易统计
        found = tx_stats['transactions_found']
        logger.info(f"💰 发现交易: {found['total']} 笔")
        for tx_type, count in found.items():
            if tx_type != 'total' and count > 0:
                logger.info(f"   {tx_type}: {count} 笔")
        
        # 代币处理统计
        if tx_stats['token_contracts_detected'] > 0:
            logger.info("🪙 代币统计:")
            logger.info(f"   合约调用检测: {tx_stats['token_contracts_detected']} 次")
            logger.info(f"   成功解析转账: {tx_stats['token_transactions_processed']} 次")
            logger.info(f"   解析成功率: {tx_stats['token_success_rate']:.1f}%")
        
        # RPC统计
        logger.info(f"🔗 RPC调用: {rpc_stats['rpc_calls']} 次")
        logger.info(f"⚡ 平均速度: {rpc_stats['avg_rpc_per_second']:.2f} 次/秒")
        logger.info(f"📊 预估日用量: {rpc_stats['estimated_daily_calls']:.0f} 次")
        logger.info(f"📈 配额使用率: {rpc_stats['api_usage_percent']:.1f}%")
        logger.info(f"🎯 缓存命中率: {rpc_stats['cache_hit_rate']:.1f}%")
        
        logger.info("🔍 RPC调用分类:")
        for call_type, count in rpc_stats['rpc_calls_by_type'].items():
            if count > 0:
                percentage = (count / rpc_stats['rpc_calls']) * 100
                logger.info(f"   {call_type}: {count} 次 ({percentage:.1f}%)")
        
        logger.info(f"✅ 速率合规: {'是' if rpc_stats['within_rate_limit'] else '否'}")
        logger.info(f"⏳ 待确认交易: {confirmation_manager.get_pending_count()} 笔")
        logger.info("=" * 80)


class EVMMonitor:
    """主监控器类 - 协调各个组件"""
    
    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()
        self.is_running = True
        
        # 初始化各个组件
        self.rpc_manager = RPCManager(self.config)
        self.tx_processor = TransactionProcessor(self.config, self.rpc_manager)
        self.confirmation_manager = ConfirmationManager(self.config, self.rpc_manager)
        self.stats_reporter = StatisticsReporter(self.config)
    
    async def start_monitoring(self) -> None:
        """开始监控"""
        # 检查网络连接
        await self._check_network_connection()
        
        # 显示启动信息
        self._log_startup_info()
        
        # 主监控循环
        await self._monitoring_loop()
    
    async def _check_network_connection(self) -> None:
        """检查网络连接"""
        try:
            latest_block = await self.rpc_manager.get_cached_block_number()
            gas_price = await self.rpc_manager.w3.eth.gas_price
            self.rpc_manager.log_rpc_call('get_gas_price')
            gas_price_gwei = self.rpc_manager.w3.from_wei(gas_price, 'gwei')
            
            logger.info(f"🌐 BNB 链连接成功 - 区块: {latest_block}, Gas: {gas_price_gwei:.2f} Gwei")
            
            # 显示支持的代币信息
            logger.info("🪙 支持的代币合约:")
            for token, contract in TokenParser.CONTRACTS.items():
                if contract:
                    logger.info(f"   {token}: {contract}")
                    
        except Exception as e:
            logger.error(f"网络连接失败: {e}")
            raise
    
    def _log_startup_info(self) -> None:
        """记录启动信息"""
        logger.info("🚀 开始监控 BNB 链交易（包含代币转账）")
        thresholds = self.config.thresholds
        logger.info(
            f"📈 监控阈值: BNB≥{thresholds['BNB']}, "
            f"USDT≥{thresholds['USDT']:,}, "
            f"USDC≥{thresholds['USDC']:,}, "
            f"BUSD≥{thresholds['BUSD']:,}"
        )
    
    async def _monitoring_loop(self) -> None:
        """主监控循环"""
        last_block = await self.rpc_manager.get_cached_block_number()
        
        while self.is_running:
            loop_start = time.time()
            
            try:
                # 处理新区块
                last_block = await self._process_new_blocks(last_block)
                
                # 检查确认状态
                await self.confirmation_manager.check_confirmations()
                
                # 定期清理和统计
                await self._periodic_maintenance()
                
                # 控制循环频率
                await self._control_loop_timing(loop_start)
                
            except Exception as e:
                logger.error(f"监控循环发生错误: {e}", exc_info=True)
                await asyncio.sleep(5)
        
        logger.info("监控已停止")
    
    async def _process_new_blocks(self, last_block: int) -> int:
        """处理新区块"""
        current_block = await self.rpc_manager.get_cached_block_number()
        await self.rpc_manager.check_rate_limit()
        
        new_blocks_processed = 0
        
        for block_number in range(last_block + 1, current_block + 1):
            if not self.is_running:
                break
            
            try:
                block = await self.rpc_manager.get_block(block_number)
                await self.rpc_manager.check_rate_limit()
                
                # 处理区块中的所有交易
                for tx in block.transactions:
                    if not self.is_running:
                        break
                    
                    tx_info = await self.tx_processor.process_transaction(tx)
                    if tx_info:
                        self.confirmation_manager.add_pending_transaction(tx_info)
                
                new_blocks_processed += 1
                self.stats_reporter.increment_blocks_processed()
                
            except BlockNotFound:
                continue
            except Exception as e:
                logger.error(f"处理区块 {block_number} 失败: {e}")
                continue
        
        # 记录处理进度
        if new_blocks_processed > 0:
            self._log_processing_progress(new_blocks_processed, current_block)
        
        return current_block
    
    def _log_processing_progress(self, new_blocks: int, current_block: int) -> None:
        """记录处理进度"""
        pending_count = self.confirmation_manager.get_pending_count()
        rpc_stats = self.rpc_manager.get_performance_stats()
        tx_stats = self.tx_processor.get_stats()
        
        logger.info(
            f"📈 处理 {new_blocks} 新区块 | "
            f"当前: {current_block} | "
            f"待确认: {pending_count} | "
            f"RPC: {rpc_stats['rpc_calls']} ({rpc_stats['avg_rpc_per_second']:.2f}/s) | "
            f"缓存: {rpc_stats['cache_hits']}/{rpc_stats['cache_hits'] + rpc_stats['cache_misses']} | "
            f"发现: {tx_stats['transactions_found']['total']}"
        )
    
    async def _periodic_maintenance(self) -> None:
        """定期维护任务"""
        current_time = time.time()
        
        # 每分钟清理一次超时交易
        if current_time % 60 < 1:
            timeout_count = self.confirmation_manager.cleanup_timeout_transactions()
            if timeout_count > 0:
                logger.info(f"清理了 {timeout_count} 个超时交易")
        
        # 定期输出统计信息
        if self.stats_reporter.should_log_stats():
            self.stats_reporter.log_performance_stats(
                self.rpc_manager, self.tx_processor, self.confirmation_manager
            )
    
    async def _control_loop_timing(self, loop_start: float) -> None:
        """控制循环时间"""
        loop_time = time.time() - loop_start
        
        if loop_time > 2:
            logger.warning(f"⚠️ 处理耗时 {loop_time:.2f}s，可能跟不上出块速度")
            await asyncio.sleep(0.1)
        else:
            await asyncio.sleep(max(0.1, 1 - loop_time))
    
    def stop(self) -> None:
        """停止监控"""
        self.is_running = False
        logger.info("正在停止监控...")
    
    def update_thresholds(self, **thresholds) -> None:
        """动态更新交易阈值"""
        for token, threshold in thresholds.items():
            if token in self.config.thresholds:
                old_threshold = self.config.thresholds[token]
                self.config.thresholds[token] = threshold
                logger.info(f"🔧 更新{token}阈值: {old_threshold} => {threshold}")
            else:
                logger.warning(f"⚠️ 未知的代币类型: {token}")
        
        logger.info(f"📈 当前阈值: {self.config.thresholds}")
    
    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """获取全面的统计信息"""
        runtime = time.time() - self.stats_reporter.start_time
        rpc_stats = self.rpc_manager.get_performance_stats()
        tx_stats = self.tx_processor.get_stats()
        
        return {
            'runtime': {
                'seconds': runtime,
                'hours': runtime / 3600
            },
            'blocks_processed': self.stats_reporter.blocks_processed,
            'transactions': tx_stats,
            'rpc_performance': rpc_stats,
            'pending_transactions': {
                'total': self.confirmation_manager.get_pending_count(),
                'by_type': self.confirmation_manager.get_pending_by_type()
            },
            'configuration': {
                'thresholds': self.config.thresholds,
                'confirmations_required': self.config.required_confirmations,
                'rate_limits': {
                    'rpc_per_second': self.config.max_rpc_per_second,
                    'rpc_per_day': self.config.max_rpc_per_day
                }
            }
        }
    
    def log_final_report(self) -> None:
        """输出最终报告"""
        self.stats_reporter.log_final_stats(
            self.rpc_manager, self.tx_processor, self.confirmation_manager
        )


async def main():
    """主函数"""
    # 创建配置（可以根据需要自定义）
    config = MonitorConfig()
    
    # 创建监控器
    monitor = EVMMonitor(config)
    
    def signal_handler(signum, frame):
        """信号处理器"""
        logger.info("接收到停止信号，正在优雅退出...")
        monitor.log_final_report()
        monitor.stop()
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 开始监控
        await monitor.start_monitoring()
    except KeyboardInterrupt:
        logger.info("接收到键盘中断，正在停止...")
    except Exception as e:
        logger.error(f"监控器启动失败: {e}", exc_info=True)
    finally:
        monitor.log_final_report()


if __name__ == '__main__':
    asyncio.run(main())