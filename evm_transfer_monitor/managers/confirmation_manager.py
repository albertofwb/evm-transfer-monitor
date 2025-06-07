"""
确认管理器

负责跟踪交易确认状态，管理待确认交易列表
支持异步通知和数据库更新
"""

import time
import asyncio
import yaml
from collections import defaultdict
from typing import Dict, List, Optional
from pathlib import Path

from config.monitor_config import MonitorConfig
from managers.rpc_manager import RPCManager
from models.data_types import TransactionInfo
from models.transaction_adapter import AsyncTransactionAdapter
from models.notification_models import NotificationRecord
from db.database import get_database_manager
from services.notification_service import NotificationService
from utils.token_parser import TokenParser
from utils.log_utils import get_logger

logger = get_logger(__name__)


class ConfirmationManager:
    """确认管理器 - 负责跟踪交易确认状态（支持异步通知和数据库更新）"""
    
    def __init__(self, config: MonitorConfig, rpc_manager: RPCManager, token_parser: TokenParser):
        self.config = config
        self.token_parser = token_parser
        self.rpc_manager = rpc_manager
        self.pending_by_block: Dict[int, List[TransactionInfo]] = defaultdict(list)
        self.last_check_time: float = 0
        
        # 数据库和通知相关
        self.db_manager = get_database_manager()
        self.notification_service = self._initialize_notification_service()
        
        # 统计信息
        self.confirmed_transactions: int = 0
        self.timeout_transactions: int = 0
        self.notifications_sent: int = 0
        self.notification_failures: int = 0
    
    def add_pending_transaction(self, tx_info: TransactionInfo) -> None:
        """添加待确认交易"""
        if tx_info.block_number:
            self.pending_by_block[tx_info.block_number].append(tx_info)
            logger.debug(f"添加待确认交易: {tx_info.hash[:10]}... (区块 {tx_info.block_number})")
    
    def _initialize_notification_service(self) -> Optional[NotificationService]:
        """初始化通知服务"""
        try:
            # 加载配置文件
            config_path = Path("config.yml")
            if not config_path.exists():
                logger.warning("配置文件不存在，通知功能将被禁用")
                return None
                
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
                
            notification_config = config_data.get('notification', {})
            if not notification_config.get('enabled', False):
                logger.info("通知功能已禁用")
                return None
                
            # 创建通知服务
            return NotificationService(
                webhook_url=notification_config.get('url', ''),
                timeout=notification_config.get('timeout', 30),
                max_retry_attempts=notification_config.get('retry_times', 3),
                retry_delay=notification_config.get('retry_delay', 5)
            )
            
        except Exception as e:
            logger.error(f"初始化通知服务失败: {e}")
            return None
    
    async def check_confirmations(self) -> None:
        """检查交易确认状态（支持异步数据库更新和通知）"""
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
        confirmed_transactions = []  # 保存已确认的交易用于后续处理
        
        for block_number, tx_list in self.pending_by_block.items():
            confirmations = current_block - block_number + 1
            
            if confirmations >= self.config.required_confirmations:
                for tx_info in tx_list:
                    self._log_confirmed_transaction(tx_info, confirmations)
                    confirmed_count += 1
                    self.confirmed_transactions += 1
                    confirmed_transactions.append((tx_info, confirmations))
                blocks_to_remove.append(block_number)
            elif confirmations <= 0:
                logger.warning(f"⚠️ 可能的区块重组，区块 {block_number} 确认数: {confirmations}")
        
        # 清理已确认的区块
        for block_number in blocks_to_remove:
            del self.pending_by_block[block_number]
        
        if confirmed_count > 0:
            logger.debug(f"本轮确认了 {confirmed_count} 个交易")
            
            # 异步处理所有已确认的交易
            if confirmed_transactions:
                asyncio.create_task(self._process_confirmed_transactions_async(confirmed_transactions))
        
        self.last_check_time = current_time
    
    def _log_confirmed_transaction(self, tx_info: TransactionInfo, confirmations: int) -> None:
        """记录已确认的交易"""
        if tx_info.tx_type == self.config.token_name:
            logger.info(
                f"✅ {self.config.token_name}交易确认: {tx_info.get_from_address()} => {tx_info.get_to_address()} | "
                f"{self.token_parser.format_amount(tx_info.value, self.config.token_name)} | "
                f"确认数: {confirmations} | {self.config.scan_url}/tx/{tx_info.hash}"
            )
        else:
            logger.info(
                f"✅ {tx_info.tx_type}交易确认: {tx_info.get_from_address()} => {tx_info.get_to_address()} | "
                f"{self.token_parser.format_amount(tx_info.value, tx_info.tx_type)} | "
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
        self.notifications_sent = 0
        self.notification_failures = 0
        logger.info("确认管理器统计数据已重置")
    
    # =============================================================================
    # 异步数据库和通知方法
    # =============================================================================
    
    async def _process_confirmed_transactions_async(self, confirmed_transactions: List[tuple]) -> None:
        """
        异步处理已确认的交易：更新数据库状态并发送通知
        
        Args:
            confirmed_transactions: [(TransactionInfo, confirmations), ...] 列表
        """
        try:
            async with self.db_manager.get_async_session() as session:
                for tx_info, confirmations in confirmed_transactions:
                    # 更新交易状态为已确认
                    success = await AsyncTransactionAdapter.update_status(
                        session, tx_info.hash, "confirmed", confirmations
                    )
                    
                    if success:
                        logger.debug(f"交易状态已更新: {tx_info.hash} -> confirmed ({confirmations} 确认)")
                        
                        # 异步发送通知
                        asyncio.create_task(self._send_notification_async(tx_info, confirmations))
                    else:
                        logger.warning(f"更新交易状态失败: {tx_info.hash}")
                        
        except Exception as e:
            logger.error(f"处理已确认交易时出错: {e}")
    
    async def _send_notification_async(self, tx_info: TransactionInfo, confirmations: int) -> None:
        """
        异步发送通知并创建通知记录
        
        Args:
            tx_info: 交易信息
            confirmations: 确认数
        """
        if not self.notification_service:
            logger.debug("通知服务未启用，跳过通知发送")
            return
            
        try:
            async with self.db_manager.get_async_session() as session:
                # 查找对应的充值记录
                deposit_records = await AsyncTransactionAdapter.get_pending_notifications(
                    session, required_confirmations=confirmations
                )
                
                # 找到对应的记录
                target_record = None
                for record in deposit_records:
                    if record.tx_hash == tx_info.hash:
                        target_record = record
                        break
                
                if not target_record:
                    logger.warning(f"未找到交易对应的充值记录: {tx_info.hash}")
                    return
                
                # 检查是否已经生成过通知
                if target_record.notification_generated:
                    logger.debug(f"交易 {tx_info.hash} 已经发送过通知，跳过")
                    return
                
                # 创建通知记录
                notification_record = NotificationRecord(
                    deposit_record_id=target_record.id,
                    tx_hash=tx_info.hash,
                    user_id=target_record.user_id,
                    notification_type='deposit',
                    status='pending'
                )
                
                # 构建通知数据
                notification_data = self._build_notification_data(target_record, confirmations)
                notification_record.request_data = str(notification_data)
                
                # 保存通知记录
                session.add(notification_record)
                await session.flush()
                
                # 发送通知
                try:
                    response = await self.notification_service.send_notification_async(notification_data)
                    
                    if response and response.get('success', False):
                        # 通知发送成功
                        notification_record.mark_as_sent(str(response))
                        target_record.mark_notification_generated()
                        self.notifications_sent += 1
                        
                        logger.info(f"✅ 通知发送成功: {tx_info.hash}")
                    else:
                        # 通知发送失败
                        error_msg = response.get('error', '未知错误') if response else '无响应'
                        notification_record.mark_as_failed(error_msg)
                        self.notification_failures += 1
                        
                        logger.warning(f"❌ 通知发送失败: {tx_info.hash} - {error_msg}")
                        
                except Exception as notify_error:
                    # 发送异常
                    notification_record.mark_as_failed(str(notify_error))
                    self.notification_failures += 1
                    logger.error(f"发送通知时出现异常: {tx_info.hash} - {notify_error}")
                
                await session.commit()
                
        except Exception as e:
            logger.error(f"处理通知时出错: {e}")
    
    def _build_notification_data(self, deposit_record, confirmations: int) -> dict:
        """
        构建通知数据
        
        Args:
            deposit_record: 充值记录
            confirmations: 确认数
            
        Returns:
            dict: 通知数据
        """
        return {
            "type": "deposit",
            "tx_hash": deposit_record.tx_hash,
            "block_number": deposit_record.block_number,
            "from_address": deposit_record.from_address,
            "to_address": deposit_record.to_address,
            "amount": str(deposit_record.amount),
            "token_symbol": deposit_record.token_symbol,
            "token_address": deposit_record.token_address or "",
            "confirmations": confirmations,
            "user_id": deposit_record.user_id,
            "timestamp": deposit_record.created_at.isoformat() if deposit_record.created_at else "",
            "gas_used": deposit_record.gas_used,
            "transaction_fee": str(deposit_record.transaction_fee) if deposit_record.transaction_fee else "0"
        }
    
    async def process_pending_notifications_async(self) -> int:
        """
        异步处理待发送的通知（用于重试失败的通知）
        
        Returns:
            int: 处理的通知数量
        """
        if not self.notification_service:
            return 0
            
        try:
            async with self.db_manager.get_async_session() as session:
                # 获取待通知的充值记录
                pending_records = await AsyncTransactionAdapter.get_pending_notifications(
                    session, self.config.required_confirmations
                )
                
                processed_count = 0
                for record in pending_records:
                    # 为每个记录异步发送通知
                    tx_info = TransactionInfo(
                        hash=record.tx_hash,
                        tx={"blockNumber": record.block_number},
                        value=float(record.amount),
                        tx_type=record.token_symbol,
                        found_at=record.created_at.timestamp() if record.created_at else 0,
                        block_number=record.block_number
                    )
                    
                    asyncio.create_task(self._send_notification_async(tx_info, record.confirmations))
                    processed_count += 1
                
                logger.info(f"异步处理了 {processed_count} 个待通知记录")
                return processed_count
                
        except Exception as e:
            logger.error(f"处理待通知记录时出错: {e}")
            return 0
