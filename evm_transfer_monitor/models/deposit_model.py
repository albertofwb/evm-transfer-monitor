"""
充值记录模型

对应 Go 版本的 DepositRecord 模型
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, DECIMAL
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from models.notification_models import NotificationRecord

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
    
    # 关联关系 - 延迟导入避免循环依赖
    notifications = relationship("NotificationRecord", back_populates="deposit_record")
    
    def is_notification_generated(self) -> bool:
        """检查是否已生成通知记录"""
        return self.notification_generated
    
    def should_generate_notification(self, required_confirmations: int) -> bool:
        """
        检查是否应该生成通知记录
        当达到要求确认数且还没有生成通知时返回True
        """
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
    
    def __repr__(self) -> str:
        return (f"<DepositRecord(id={self.id}, tx_hash='{self.tx_hash[:10]}...', "
                f"amount={self.amount}, status='{self.status}')>")
