"""
数据适配器

将 TransactionInfo 对象转换并保存到数据库中的 deposit_records 表
支持同步和异步操作
"""

import asyncio
from typing import Optional, Dict, Any, List
from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .data_types import TransactionInfo
from .deposit_model import DepositRecord
from utils.log_utils import get_logger

logger = get_logger(__name__)


class TransactionAdapter:
    """交易信息适配器，用于将 TransactionInfo 保存到数据库（支持同步和异步）"""
    
    def __init__(self, db_session: Optional[Session] = None):
        self.db_session = db_session
    
    def save_transaction_info(self, transaction_info: TransactionInfo, user_id: str = "") -> Optional[DepositRecord]:
        """
        将 TransactionInfo 保存到 deposit_records 表中
        
        Args:
            transaction_info: TransactionInfo 对象
            user_id: 用户ID，如果未提供将尝试从交易中推断
            
        Returns:
            DepositRecord: 保存的记录对象，如果失败返回None
        """
        if not self.db_session:
            raise RuntimeError("需要提供同步数据库会话")
            
        try:
            # 检查交易是否已存在
            existing_record = self.db_session.query(DepositRecord).filter(
                DepositRecord.tx_hash == transaction_info.hash
            ).first()
            
            if existing_record:
                logger.info(f"交易 {transaction_info.hash} 已存在，跳过保存")
                return existing_record
            
            # 创建新的充值记录
            deposit_record = DepositRecord()
            
            # 基础交易信息
            deposit_record.tx_hash = transaction_info.hash
            deposit_record.block_number = transaction_info.block_number
            deposit_record.block_hash = transaction_info.tx.get('blockHash', '')
            deposit_record.from_address = transaction_info.get_from_address()
            deposit_record.to_address = transaction_info.get_to_address()
            deposit_record.status = 'pending'  # 新交易默认为pending状态
            deposit_record.confirmations = 0   # 初始确认数为0
            
            # Gas 相关信息
            if 'gasUsed' in transaction_info.tx:
                deposit_record.gas_used = int(transaction_info.tx['gasUsed'], 16) if isinstance(transaction_info.tx['gasUsed'], str) else transaction_info.tx['gasUsed']
            
            if 'gasPrice' in transaction_info.tx:
                gas_price_wei = int(transaction_info.tx['gasPrice'], 16) if isinstance(transaction_info.tx['gasPrice'], str) else transaction_info.tx['gasPrice']
                deposit_record.gas_price = Decimal(gas_price_wei) / Decimal(10**18)  # 转换为 ETH
            
            # 计算交易费用
            if deposit_record.gas_used and deposit_record.gas_price:
                deposit_record.transaction_fee = deposit_record.gas_price * Decimal(deposit_record.gas_used)
            
            # 处理代币交易
            if transaction_info.is_token_transaction() and transaction_info.token_info:
                self._handle_token_transaction(deposit_record, transaction_info)
            else:
                self._handle_native_transaction(deposit_record, transaction_info)
            
            # 用户ID处理
            deposit_record.user_id = user_id or self._extract_user_id(transaction_info)
            
            # 保存到数据库
            self.db_session.add(deposit_record)
            self.db_session.commit()
            
            logger.info(f"成功保存交易记录: {transaction_info.hash}")
            return deposit_record
            
        except Exception as e:
            logger.error(f"保存交易信息时出错: {e}")
            self.db_session.rollback()
            return None
    
    def _handle_token_transaction(self, deposit_record: DepositRecord, transaction_info: TransactionInfo) -> None:
        """处理代币交易"""
        token_info = transaction_info.token_info
        
        # 代币基础信息
        deposit_record.token_address = token_info.get('contract_address', '')
        deposit_record.token_symbol = token_info.get('symbol', 'UNKNOWN')
        deposit_record.token_decimals = token_info.get('decimals', 18)
        
        # 代币金额（已经是实际数量，不需要再次转换）
        deposit_record.amount = Decimal(str(transaction_info.value))
        
        logger.debug(f"处理代币交易: {deposit_record.token_symbol}, 数量: {deposit_record.amount}")
    
    def _handle_native_transaction(self, deposit_record: DepositRecord, transaction_info: TransactionInfo) -> None:
        """处理原生代币交易"""
        # 原生代币信息
        deposit_record.token_address = ""  # 空表示原生代币
        deposit_record.token_symbol = "ETH"  # 默认为ETH，可根据实际链调整
        deposit_record.token_decimals = 18
        
        # 原生代币金额
        deposit_record.amount = Decimal(str(transaction_info.value))
        
        logger.debug(f"处理原生代币交易: ETH, 数量: {deposit_record.amount}")
    
    def _extract_user_id(self, transaction_info: TransactionInfo) -> str:
        """
        从交易信息中提取用户ID
        
        这里需要根据业务逻辑来实现，比如：
        - 通过接收地址查找对应的用户
        - 从交易的input data中解析
        - 使用其他业务规则
        """
        # 默认实现：使用接收地址作为用户标识
        to_address = transaction_info.get_to_address()
        return to_address.lower() if to_address else ""
    
    def update_transaction_status(self, tx_hash: str, status: str, confirmations: int = 0) -> bool:
        """
        更新交易状态和确认数
        
        Args:
            tx_hash: 交易哈希
            status: 新状态
            confirmations: 确认数
            
        Returns:
            bool: 更新是否成功
        """
        if not self.db_session:
            raise RuntimeError("需要提供同步数据库会话")
            
        try:
            record = self.db_session.query(DepositRecord).filter(
                DepositRecord.tx_hash == tx_hash
            ).first()
            
            if not record:
                logger.warning(f"未找到交易记录: {tx_hash}")
                return False
            
            record.status = status
            record.confirmations = confirmations
            
            self.db_session.commit()
            logger.debug(f"更新交易状态: {tx_hash} -> {status} ({confirmations} 确认)")
            return True
            
        except Exception as e:
            logger.error(f"更新交易状态时出错: {e}")
            self.db_session.rollback()
            return False
    
    def get_pending_notifications(self, required_confirmations: int = 12) -> list[DepositRecord]:
        """
        获取需要生成通知的充值记录
        
        Args:
            required_confirmations: 所需确认数
            
        Returns:
            list[DepositRecord]: 需要通知的记录列表
        """
        if not self.db_session:
            raise RuntimeError("需要提供同步数据库会话")
            
        try:
            records = self.db_session.query(DepositRecord).filter(
                DepositRecord.status == 'confirmed',
                DepositRecord.confirmations >= required_confirmations,
                DepositRecord.notification_generated == False
            ).all()
            
            return records
            
        except Exception as e:
            logger.error(f"获取待通知记录时出错: {e}")
            return []
    
    def batch_save_transactions(self, transaction_infos: list[TransactionInfo], user_id: str = "") -> int:
        """
        批量保存交易信息
        
        Args:
            transaction_infos: TransactionInfo 对象列表
            user_id: 用户ID
            
        Returns:
            int: 成功保存的记录数
        """
        saved_count = 0
        
        for transaction_info in transaction_infos:
            if self.save_transaction_info(transaction_info, user_id):
                saved_count += 1
        
        logger.info(f"批量保存完成，成功保存 {saved_count}/{len(transaction_infos)} 条记录")
        return saved_count
    
    # =============================================================================
    # 异步方法
    # =============================================================================
    
    async def save_transaction_info_async(self, async_session: AsyncSession, 
                                         transaction_info: TransactionInfo, 
                                         user_id: str = "") -> Optional[DepositRecord]:
        """
        异步保存 TransactionInfo 到 deposit_records 表
        
        Args:
            async_session: 异步数据库会话
            transaction_info: TransactionInfo 对象
            user_id: 用户ID
            
        Returns:
            DepositRecord: 保存的记录对象，失败返回None
        """
        try:
            # 检查交易是否已存在
            result = await async_session.execute(
                select(DepositRecord).where(DepositRecord.tx_hash == transaction_info.hash)
            )
            existing_record = result.scalar_one_or_none()
            
            if existing_record:
                logger.info(f"交易 {transaction_info.hash} 已存在，跳过保存")
                return existing_record
            
            # 创建新的充值记录
            deposit_record = DepositRecord()
            
            # 基础交易信息
            deposit_record.tx_hash = transaction_info.hash
            deposit_record.block_number = transaction_info.block_number
            deposit_record.block_hash = transaction_info.tx.get('blockHash', '')
            deposit_record.from_address = transaction_info.get_from_address()
            deposit_record.to_address = transaction_info.get_to_address()
            deposit_record.status = 'pending'  # 新交易默认为pending状态
            deposit_record.confirmations = 0   # 初始确认数为0
            
            # Gas 相关信息
            if 'gasUsed' in transaction_info.tx:
                gas_used = transaction_info.tx['gasUsed']
                if isinstance(gas_used, str):
                    deposit_record.gas_used = int(gas_used, 16)
                else:
                    deposit_record.gas_used = gas_used
            
            if 'gasPrice' in transaction_info.tx:
                gas_price = transaction_info.tx['gasPrice']
                if isinstance(gas_price, str):
                    gas_price_wei = int(gas_price, 16)
                else:
                    gas_price_wei = gas_price
                deposit_record.gas_price = Decimal(gas_price_wei) / Decimal(10**18)
            
            # 计算交易费用
            if deposit_record.gas_used and deposit_record.gas_price:
                deposit_record.transaction_fee = deposit_record.gas_price * Decimal(deposit_record.gas_used)
            
            # 处理代币交易
            if transaction_info.is_token_transaction() and transaction_info.token_info:
                self._handle_token_transaction(deposit_record, transaction_info)
            else:
                self._handle_native_transaction(deposit_record, transaction_info)
            
            # 用户ID处理
            deposit_record.user_id = user_id or self._extract_user_id(transaction_info)
            
            # 保存到数据库
            async_session.add(deposit_record)
            await async_session.flush()  # 立即刷新获取ID
            
            logger.info(f"成功保存交易记录: {transaction_info.hash}")
            return deposit_record
            
        except Exception as e:
            logger.error(f"异步保存交易信息时出错: {e}")
            await async_session.rollback()
            return None
    
    async def update_transaction_status_async(self, async_session: AsyncSession, 
                                            tx_hash: str, status: str, 
                                            confirmations: int = 0) -> bool:
        """
        异步更新交易状态和确认数
        
        Args:
            async_session: 异步数据库会话
            tx_hash: 交易哈希
            status: 新状态
            confirmations: 确认数
            
        Returns:
            bool: 更新是否成功
        """
        try:
            result = await async_session.execute(
                select(DepositRecord).where(DepositRecord.tx_hash == tx_hash)
            )
            record = result.scalar_one_or_none()
            
            if not record:
                logger.warning(f"未找到交易记录: {tx_hash}")
                return False
            
            record.status = status
            record.confirmations = confirmations
            
            await async_session.flush()
            logger.debug(f"更新交易状态: {tx_hash} -> {status} ({confirmations} 确认)")
            return True
            
        except Exception as e:
            logger.error(f"异步更新交易状态时出错: {e}")
            return False
    
    async def get_pending_notifications_async(self, async_session: AsyncSession, 
                                            required_confirmations: int = 12) -> List[DepositRecord]:
        """
        异步获取需要生成通知的充值记录
        
        Args:
            async_session: 异步数据库会话
            required_confirmations: 所需确认数
            
        Returns:
            List[DepositRecord]: 需要通知的记录列表
        """
        try:
            result = await async_session.execute(
                select(DepositRecord).where(
                    DepositRecord.status == 'confirmed',
                    DepositRecord.confirmations >= required_confirmations,
                    DepositRecord.notification_generated == False
                )
            )
            records = result.scalars().all()
            return list(records)
            
        except Exception as e:
            logger.error(f"异步获取待通知记录时出错: {e}")
            return []
    
    async def batch_save_transactions_async(self, async_session: AsyncSession, 
                                          transaction_infos: List[TransactionInfo], 
                                          user_id: str = "") -> int:
        """
        异步批量保存交易信息
        
        Args:
            async_session: 异步数据库会话
            transaction_infos: TransactionInfo 对象列表
            user_id: 用户ID
            
        Returns:
            int: 成功保存的记录数
        """
        saved_count = 0
        
        for transaction_info in transaction_infos:
            if await self.save_transaction_info_async(async_session, transaction_info, user_id):
                saved_count += 1
        
        logger.info(f"异步批量保存完成，成功保存 {saved_count}/{len(transaction_infos)} 条记录")
        return saved_count


class AsyncTransactionAdapter:
    """
    纯异步交易适配器，专门用于异步操作
    推荐在需要高性能的地方使用
    """
    
    @staticmethod
    async def save_transaction(async_session: AsyncSession, 
                             transaction_info: TransactionInfo, 
                             user_id: str = "") -> Optional[DepositRecord]:
        """静态方法：异步保存交易信息"""
        adapter = TransactionAdapter()
        return await adapter.save_transaction_info_async(async_session, transaction_info, user_id)
    
    @staticmethod
    async def update_status(async_session: AsyncSession, 
                          tx_hash: str, status: str, 
                          confirmations: int = 0) -> bool:
        """静态方法：异步更新交易状态"""
        adapter = TransactionAdapter()
        return await adapter.update_transaction_status_async(async_session, tx_hash, status, confirmations)
    
    @staticmethod
    async def get_pending_notifications(async_session: AsyncSession, 
                                      required_confirmations: int = 12) -> List[DepositRecord]:
        """静态方法：异步获取待通知记录"""
        adapter = TransactionAdapter()
        return await adapter.get_pending_notifications_async(async_session, required_confirmations)
    
    @staticmethod
    async def batch_save(async_session: AsyncSession, 
                        transaction_infos: List[TransactionInfo], 
                        user_id: str = "") -> int:
        """静态方法：异步批量保存交易信息"""
        adapter = TransactionAdapter()
        return await adapter.batch_save_transactions_async(async_session, transaction_infos, user_id)
