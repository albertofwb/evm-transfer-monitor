"""
交易处理器

负责检测和分析区块链交易，识别大额转账
"""

import time
from collections import defaultdict
from typing import Dict, Any, Optional

from monitor_config import MonitorConfig
from rpc_manager import RPCManager
from data_types import TransactionInfo, TransactionStats
from token_parser import TokenParser
from log_utils import get_logger

logger = get_logger(__name__)


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
        """处理原生代币交易"""
        wei = tx['value']
        token_amount = self.rpc_manager.w3.from_wei(wei, 'ether')
        
        if token_amount >= self.config.get_threshold(self.config.token_name):
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
        
        return None
    
    def _log_native_transaction(self, tx: Dict[str, Any], amount: float, 
                              gas_cost: float, block_number: int, tx_hash: str) -> None:
        """记录原生代币交易日志"""
        logger.info(
            f"💰 大额 {self.config.token_name}: {tx['from']} => {tx['to']} | "
            f"{TokenParser.format_amount(amount, self.config.token_name)} | "
            f"Gas: {gas_cost:,.5f} {self.config.token_name} | "
            f"区块: {block_number} | {self.config.scan_url}/tx/{tx_hash}"
        )
    
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
        threshold = self.config.get_threshold(token_symbol)
        if token_info['amount'] >= threshold:
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
        
        logger.info(
            f"{icon} 大额{token_symbol}: {token_info['from']} => {token_info['to']} | "
            f"{TokenParser.format_amount(token_info['amount'], token_symbol)} | "
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
        """更新交易阈值"""
        self.config.update_thresholds(**new_thresholds)
        logger.info(f"交易阈值已更新: {self.config.thresholds}")
