"""
交易处理器

负责检测和分析区块链交易，支持两种监控策略：
1. 大额交易监控 - 检测超过阈值的交易
2. 指定地址监控 - 检测发送到特定地址的交易
"""

import time
from collections import defaultdict
from typing import Dict, Any, Optional
from utils.token_parser import TokenParser
from config.monitor_config import MonitorConfig
from managers.rpc_manager import RPCManager
from models.data_types import TransactionInfo, TransactionStats
from utils.log_utils import get_logger

logger = get_logger(__name__)


class TransactionProcessor:
    """交易处理器 - 负责检测和分析交易"""

    def __init__(self, config: MonitorConfig, token_parser: TokenParser, rpc_manager: RPCManager):
        self.config = config
        self.token_parser = token_parser
        self.rpc_manager = rpc_manager

        # 统计信息
        self.transactions_found: Dict[str, int] = defaultdict(int)
        self.token_contracts_detected: int = 0
        self.token_transactions_processed: int = 0
    
    async def process_transaction(self, tx: Dict[str, Any]) -> Optional[TransactionInfo]:
        """处理单个交易，根据配置的策略进行检测"""
        block_number = tx.get('blockNumber')
        
        # 检测原生代币转账
        native_info = self._process_native_transaction(tx, block_number)
        if native_info:
            return native_info
        
        # 检测代币转账
        token_info = self._process_token_transaction(tx, block_number)
        if token_info:
            return token_info
        
        return None
    
    def _process_native_transaction(self, tx: Dict[str, Any], block_number: int) -> Optional[TransactionInfo]:
        """处理原生代币交易，根据策略检测"""
        wei = tx['value']
        if wei == 0:
            return None
            
        token_amount = self.rpc_manager.w3.from_wei(wei, 'ether')
        
        # 根据策略检测
        if self.config.is_large_amount_strategy():
            # 大额交易策略：检查金额阈值
            if token_amount < self.config.get_threshold(self.config.token_name):
                return None
        elif self.config.is_watch_address_strategy():
            # 地址监控策略：检查接收地址
            to_address = tx.get('to')
            if not to_address or not self.config.is_watched_address(to_address):
                return None
        else:
            return None
        
        # 记录交易
        gas_cost = self.rpc_manager.w3.from_wei(tx['gasPrice'] * tx['gas'], 'ether')
        tx_hash = self.rpc_manager.w3.to_hex(tx['hash'])
        
        self._log_native_transaction(tx, token_amount, gas_cost, block_number, tx_hash)
        
        self.transactions_found[self.config.token_name] += 1
        self.transactions_found['total'] += 1
        
        return TransactionInfo(
            hash=tx_hash,
            tx=tx,
            value=token_amount,
            tx_type=self.config.token_name,
            found_at=time.time(),
            block_number=block_number
        )
    
    def _log_native_transaction(self, tx: Dict[str, Any], amount: float, 
                              gas_cost: float, block_number: int, tx_hash: str) -> None:
        """记录原生代币交易日志"""
        if self.config.is_large_amount_strategy():
            prefix = f"💰 大额 {self.config.token_name}"
        else:
            prefix = f"📨 接收 {self.config.token_name}"
            
        logger.info(
            f"{prefix}: {tx['from']} => {tx['to']} | "
            f"{self.token_parser.format_amount(amount, self.config.token_name)} | "
            f"Gas: {gas_cost:,.5f} {self.config.token_name} | "
            f"区块: {block_number} | {self.config.scan_url}/tx/{tx_hash}"
        )
    
    def _process_token_transaction(self, tx: Dict[str, Any], block_number: int) -> Optional[TransactionInfo]:
        """处理代币交易，根据策略检测"""
        if not tx.get('to'):
            return None
        
        # 检查是否为支持的代币合约
        token_symbol = self.token_parser.is_token_contract(tx['to'])
        if not token_symbol:
            return None
        
        self.token_contracts_detected += 1
        
        # 解析代币转账
        token_info = self.token_parser.parse_erc20_transfer(tx, token_symbol)
        if not token_info:
            return None
        
        self.token_transactions_processed += 1
        
        # 根据策略检测
        should_process = False
        
        if self.config.is_large_amount_strategy():
            to_address = token_info.get('to').lower()
            # 大额交易策略：检查金额阈值
            threshold = self.config.get_threshold(token_symbol)
            should_process = token_info['amount'] >= threshold and to_address
        elif self.config.is_watch_address_strategy():
            # 地址监控策略：检查接收地址
            to_address = token_info.get('to').lower()
            from_address = token_info.get('from').lower()
            should_process = to_address and self.config.is_watched_address(to_address) and to_address != from_address

        if should_process:
            tx_hash = self.rpc_manager.w3.to_hex(tx['hash'])
            self._log_token_transaction(token_info, token_symbol, block_number, tx_hash)
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
    
    def _log_token_transaction(self, token_info: Dict[str, Any], token_symbol: str, 
                             block_number: int, tx_hash: str) -> None:
        """记录代币交易日志"""
        # 根据代币类型选择图标
        icons = {'USDT': '💵', 'USDC': '💸'}
        icon = icons.get(token_symbol, '🪙')
        
        if self.config.is_large_amount_strategy():
            prefix = f"{icon} 大额{token_symbol}"
        else:
            prefix = f"{icon} 接收{token_symbol}"
        
        logger.info(
            f"{prefix}: {token_info['from']} => {token_info['to']} | "
            f"{self.token_parser.format_amount(token_info['amount'], token_symbol)} | "
            f"区块: {block_number} | {self.config.scan_url}/tx/{tx_hash}"
        )
    
    def get_stats(self) -> TransactionStats:
        """获取处理统计信息"""
        success_rate = 0
        if self.token_contracts_detected > 0:
            success_rate = (self.token_transactions_processed / self.token_contracts_detected) * 100
        
        return TransactionStats(
            transactions_found=dict(self.transactions_found),
            token_contracts_detected=self.token_contracts_detected,
            token_transactions_processed=self.token_transactions_processed,
            token_success_rate=success_rate
        )
    
    def reset_stats(self) -> None:
        """重置统计数据"""
        self.transactions_found.clear()
        self.token_contracts_detected = 0
        self.token_transactions_processed = 0
        logger.info("交易处理统计数据已重置")
    
    def get_transaction_summary(self) -> Dict[str, Any]:
        """获取交易摘要信息"""
        stats = self.get_stats()
        return {
            'total_found': stats.transactions_found.get('total', 0),
            'by_type': {k: v for k, v in stats.transactions_found.items() if k != 'total'},
            'token_processing': {
                'contracts_detected': stats.token_contracts_detected,
                'transactions_processed': stats.token_transactions_processed,
                'success_rate': f"{stats.token_success_rate:.1f}%"
            }
        }
    
    def update_thresholds(self, **new_thresholds) -> None:
        """更新交易阈值（仅在大额交易策略下有效）"""
        if not self.config.is_large_amount_strategy():
            logger.warning("当前策略为地址监控，阈值设置无效")
            return
        
        self.config.update_thresholds(**new_thresholds)
        logger.info(f"交易阈值已更新: {self.config.thresholds}")
