"""
数据库模型定义

使用 SQLAlchemy 定义数据库表结构，对应 Go 版本的模型
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, DECIMAL, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from decimal import Decimal
import uuid
from datetime import datetime
from typing import Optional

Base = declarative_base()


class DepositRecord(Base):
    """充值记录模型 - 对应 Go 版本的 DepositRecord"""
    
    __tablename__ = 'deposit_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tx_hash = Column(String(66), unique=True, nullable=False, index=True)
    block_number = Column(Integer)
    block_hash = Column(String(66))
    from_address = Column(String(42))
    to_address = Column(String(42))
    amount = Column(DECIMAL(36, 18))
    token_address = Column(String(42))  # 空表示原生代币
    token_symbol = Column(String(20))
    token_decimals = Column(Integer)
    status = Column(String(20), default='pending')  # pending, confirmed, failed
    confirmations = Column(Integer, default=0)
    notification_generated = Column(Boolean, default=False, index=True)  # 标记是否已生成通知记录
    gas_used = Column(Integer)
    gas_price = Column(DECIMAL(36, 18))
    transaction_fee = Column(DECIMAL(36, 18))
    user_id = Column(String(50))
    processed_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # 关联关系
    notifications = relationship("NotificationRecord", back_populates="deposit_record")
    
    def is_notification_generated(self) -> bool:
        """检查是否已生成通知记录"""
        return self.notification_generated
    
    def should_generate_notification(self, required_confirmations: int) -> bool:
        """检查是否应该生成通知记录"""
        return (self.status == "confirmed" and 
                self.confirmations >= required_confirmations and 
                not self.notification_generated)
    
    def mark_notification_generated(self) -> None:
        """标记已生成通知记录"""
        self.notification_generated = True
        if self.processed_at is None:
            self.processed_at = datetime.now()
    
    def get_confirmation_progress(self, required_confirmations: int) -> str:
        """获取确认进度描述"""
        if self.status != "confirmed":
            return f"状态: {self.status}"
        
        if self.confirmations < required_confirmations:
            return f"确认中 ({self.confirmations}/{required_confirmations})"
        
        if self.notification_generated:
            return "已确认并通知"
        
        return "已确认待通知"


class NotificationRecord(Base):
    """通知记录模型 - 对应 Go 版本的 NotificationRecord"""
    
    __tablename__ = 'notification_records'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deposit_record_id = Column(Integer, ForeignKey('deposit_records.id'), nullable=False, index=True)
    tx_hash = Column(String(66), nullable=False, index=True)  # 交易哈希，用于快速查询
    user_id = Column(String(50), nullable=False, index=True)
    notification_type = Column(String(20), nullable=False, default='deposit')  # deposit, withdrawal, etc.
    status = Column(String(20), nullable=False, default='pending')  # pending, sent, failed, retry, failed_final
    attempt_count = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    last_attempt_at = Column(DateTime)
    success_at = Column(DateTime)
    request_data = Column(Text)  # 请求数据（JSON格式）
    response_data = Column(Text)  # 响应数据
    error_message = Column(Text)
    next_retry_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # 关联关系
    deposit_record = relationship("DepositRecord", back_populates="notifications")
    
    def is_max_attempts_reached(self) -> bool:
        """检查是否达到最大重试次数"""
        return self.attempt_count >= self.max_attempts
    
    def can_retry(self) -> bool:
        """检查是否可以重试"""
        if self.status == "sent":
            return False
        if self.is_max_attempts_reached():
            return False
        if self.next_retry_at and datetime.now() < self.next_retry_at:
            return False
        return True
    
    def mark_as_sent(self, response_data: str = "") -> None:
        """标记为已发送"""
        now = datetime.now()
        self.status = "sent"
        self.success_at = now
        self.last_attempt_at = now
        self.response_data = response_data
        self.error_message = ""
    
    def mark_as_failed(self, error_msg: str, next_retry_at: Optional[datetime] = None) -> None:
        """标记为失败"""
        now = datetime.now()
        self.status = "failed"
        self.last_attempt_at = now
        self.error_message = error_msg
        self.next_retry_at = next_retry_at
        
        # 如果达到最大重试次数，标记为最终失败
        if self.is_max_attempts_reached():
            self.status = "failed_final"
            self.next_retry_at = None
    
    def increment_attempt(self) -> None:
        """增加尝试次数"""
        self.attempt_count += 1
