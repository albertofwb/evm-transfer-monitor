"""
确认管理器

负责跟踪交易确认状态，管理待确认交易列表
"""

import time
from collections import defaultdict
from typing import Dict, List

from monitor_config import MonitorConfig
from rpc_manager import RPCManager
from data_types import TransactionInfo
from token_parser import TokenParser
from log_utils import get_logger

logger = get_logger(__name__)


class ConfirmationManager:
    """确认管理器 - 负责跟踪交易确认状态"""
    
    def __init__(self, config: MonitorConfig, rpc_manager: RPCManager):
        self.config = config
        self.rpc_manager = rpc_manager
        self.pending_by_block: Dict[int, List[TransactionInfo]] = defaultdict(list)
        self.last_check_time: float = 0
        
        # 统计信息
        self.confirmed_transactions: int = 0
        self.timeout_transactions: int = 0
    
    def add_pending_transaction(self, tx_info: TransactionInfo) -> None:
        """添加待确认交易"""
        if tx_info.block_number:
            self.pending_by_block[tx_info.block_number].append(tx_info)
            logger.debug(f"添加待确认交易: {tx_info.hash[:10]}... (区块 {tx_info.block_number})")
    
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
                    self.confirmed_transactions += 1
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
        if tx_info.tx_type == self.config.token_name:
            logger.info(
                f"✅ {self.config.token_name}交易确认: {tx_info.get_from_address()} => {tx_info.get_to_address()} | "
                f"{TokenParser.format_amount(tx_info.value, self.config.token_name)} | "
                f"确认数: {confirmations} | {self.config.scan_url}/tx/{tx_info.hash}"
            )
        else:
            logger.info(
                f"✅ {tx_info.tx_type}交易确认: {tx_info.get_from_address()} => {tx_info.get_to_address()} | "
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
                    self.timeout_transactions += 1
                    logger.warning(f"⏰ {tx_info.tx_type}交易确认超时: {tx_info.hash}")
            
            if remaining_txs:
                self.pending_by_block[block_number] = remaining_txs
            else:
                blocks_to_remove.append(block_number)
        
        for block_number in blocks_to_remove:
            del self.pending_by_block[block_number]
        
        if timeout_count > 0:
            logger.info(f"清理了 {timeout_count} 个超时交易")
        
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
    
    def get_pending_by_block(self) -> Dict[int, int]:
        """按区块统计待确认交易"""
        return {block: len(txs) for block, txs in self.pending_by_block.items()}
    
    def get_oldest_pending_age(self) -> float:
        """获取最老的待确认交易年龄（秒）"""
        if not self.pending_by_block:
            return 0.0
        
        current_time = time.time()
        oldest_time = current_time
        
        for tx_list in self.pending_by_block.values():
            for tx_info in tx_list:
                oldest_time = min(oldest_time, tx_info.found_at)
        
        return current_time - oldest_time
    
    def get_stats(self) -> Dict[str, any]:
        """获取确认管理器统计信息"""
        return {
            'pending_count': self.get_pending_count(),
            'pending_by_type': self.get_pending_by_type(),
            'pending_by_block': self.get_pending_by_block(),
            'confirmed_transactions': self.confirmed_transactions,
            'timeout_transactions': self.timeout_transactions,
            'oldest_pending_age': self.get_oldest_pending_age(),
            'blocks_with_pending': len(self.pending_by_block)
        }
    
    def clear_all_pending(self) -> int:
        """清空所有待确认交易"""
        total_cleared = self.get_pending_count()
        self.pending_by_block.clear()
        logger.info(f"清空了 {total_cleared} 个待确认交易")
        return total_cleared
    
    def has_pending_transactions(self) -> bool:
        """检查是否有待确认交易"""
        return len(self.pending_by_block) > 0
    
    def reset_stats(self) -> None:
        """重置统计数据"""
        self.confirmed_transactions = 0
        self.timeout_transactions = 0
        logger.info("确认管理器统计数据已重置")
