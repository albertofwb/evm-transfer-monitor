"""
通知调度器

实现通知的定时调度、重试和清理功能
"""

import logging
import threading
import time
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from services.notification_service import NotificationService, NotificationConfig
from models.notification_models import DepositRecord


logger = logging.getLogger(__name__)


class NotificationScheduler:
    """通知调度器"""
    
    def __init__(self, db_session: Session, notification_service: NotificationService, 
                 config: NotificationConfig):
        self.db_session = db_session
        self.notification_service = notification_service
        self.config = config
        
        # 配置定时间隔
        self.retry_interval = getattr(config, 'retry_delay', 10)  # 默认10秒
        self.cleanup_interval = 24 * 3600  # 24小时清理一次
        
        # 控制变量
        self._running = False
        self._stop_event = threading.Event()
        self._retry_thread: Optional[threading.Thread] = None
        self._cleanup_thread: Optional[threading.Thread] = None
    
    def start(self) -> None:
        """启动通知调度器"""
        if self._running:
            logger.warning("通知调度器已经在运行")
            return
        
        logger.info(f"通知调度器启动 [enabled: {self.config.enabled}, "
                   f"retry_interval: {self.retry_interval}s, "
                   f"cleanup_interval: {self.cleanup_interval}s]")
        
        if not self.config.enabled:
            logger.info("通知功能已禁用，调度器将不执行任何操作")
            return
        
        self._running = True
        self._stop_event.clear()
        
        # 启动重试失败通知的线程
        self._retry_thread = threading.Thread(
            target=self._retry_failed_notifications_loop,
            name="NotificationRetryThread",
            daemon=True
        )
        self._retry_thread.start()
        
        # 启动清理旧记录的线程
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_old_notifications_loop,
            name="NotificationCleanupThread",
            daemon=True
        )
        self._cleanup_thread.start()
        
        logger.info("通知调度器已启动")
    
    def stop(self) -> None:
        """停止通知调度器"""
        if not self._running:
            return
        
        logger.info("正在停止通知调度器...")
        
        self._running = False
        self._stop_event.set()
        
        # 等待线程结束
        if self._retry_thread and self._retry_thread.is_alive():
            self._retry_thread.join(timeout=5)
        
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)
        
        logger.info("通知调度器已停止")
    
    def process_pending_notifications(self, required_confirmations: int = 12) -> int:
        """
        处理待通知的充值记录
        
        Args:
            required_confirmations: 所需确认数
            
        Returns:
            int: 处理的记录数
        """
        if not self.config.enabled:
            return 0
        
        try:
            # 如果没有数据库会话或模型不存在，返回 0
            if not self.db_session:
                logger.debug("没有数据库会话，跳过待通知处理")
                return 0
            
            # 检查是否有真实的 DepositRecord 模型
            if not hasattr(DepositRecord, '__table__'):
                logger.debug("没有真实的 DepositRecord 模型，跳过待通知处理")
                return 0
            
            # 查找需要生成通知的充值记录
            pending_records = self.db_session.query(DepositRecord).filter(
                DepositRecord.status == 'confirmed',
                DepositRecord.confirmations >= required_confirmations,
                DepositRecord.notification_generated == False
            ).limit(50).all()  # 限制批次大小
            
            processed_count = 0
            for record in pending_records:
                notification = self.notification_service.create_notification_record(record)
                if notification:
                    # 立即尝试发送通知
                    result = self.notification_service.send_notification(notification)
                    if result.get('success', False):
                        # 更新记录状态
                        record.notification_generated = True
                        self.db_session.commit()
                    processed_count += 1
            
            if processed_count > 0:
                logger.info(f"处理待通知记录: {processed_count} 条")
            
            return processed_count
            
        except Exception as e:
            logger.error(f"处理待通知记录时出错: {e}")
            if self.db_session:
                try:
                    self.db_session.rollback()
                except:
                    pass
            return 0
    
    def _retry_failed_notifications_loop(self) -> None:
        """重试失败通知的循环"""
        logger.info(f"启动通知重试任务，间隔: {self.retry_interval}s")
        
        while not self._stop_event.is_set():
            try:
                if self.config.enabled:
                    self._retry_failed_notifications()
                
                # 等待下次执行
                if self._stop_event.wait(timeout=self.retry_interval):
                    break
                    
            except Exception as e:
                logger.error(f"重试失败通知任务发生异常: {e}")
                # 发生异常时等待一段时间再继续
                if self._stop_event.wait(timeout=30):
                    break
        
        logger.info("重试失败通知任务已停止")
    
    def _cleanup_old_notifications_loop(self) -> None:
        """清理旧记录的循环"""
        logger.info(f"启动清理旧通知记录任务，间隔: {self.cleanup_interval}s")
        
        while not self._stop_event.is_set():
            try:
                if self.config.enabled:
                    self._cleanup_old_notifications()
                
                # 等待下次执行
                if self._stop_event.wait(timeout=self.cleanup_interval):
                    break
                    
            except Exception as e:
                logger.error(f"清理旧通知记录任务发生异常: {e}")
                # 发生异常时等待一段时间再继续
                if self._stop_event.wait(timeout=300):  # 5分钟
                    break
        
        logger.info("清理旧通知记录任务已停止")
    
    def _retry_failed_notifications(self) -> None:
        """重试失败的通知"""
        try:
            count = self.notification_service.retry_failed_notifications()
            if count > 0:
                logger.debug(f"重试通知: {count} 条")
        except Exception as e:
            logger.error(f"重试失败通知时出错: {e}")
    
    def _cleanup_old_notifications(self) -> None:
        """清理旧的通知记录"""
        try:
            # 使用配置中的清理天数，默认保留30天的记录
            cleanup_days = getattr(self.config, 'cleanup_days', 30)
            count = self.notification_service.cleanup_old_notifications(cleanup_days)
            if count > 0:
                logger.info(f"清理旧通知记录: {count} 条")
        except Exception as e:
            logger.error(f"清理旧通知记录时出错: {e}")
    
    def set_retry_interval(self, interval: int) -> None:
        """设置重试间隔"""
        self.retry_interval = interval
        logger.info(f"重试间隔已设置为: {interval}s")
    
    def set_cleanup_interval(self, interval: int) -> None:
        """设置清理间隔"""
        self.cleanup_interval = interval
        logger.info(f"清理间隔已设置为: {interval}s")
    
    def is_running(self) -> bool:
        """检查调度器是否运行中"""
        return self._running
    
    def get_status(self) -> dict:
        """获取调度器状态"""
        return {
            "running": self._running,
            "enabled": self.config.enabled,
            "retry_interval": self.retry_interval,
            "cleanup_interval": self.cleanup_interval,
            "retry_thread_alive": self._retry_thread.is_alive() if self._retry_thread else False,
            "cleanup_thread_alive": self._cleanup_thread.is_alive() if self._cleanup_thread else False,
            "notification_stats": self.notification_service.get_stats()
        }


# 上下文管理器，用于自动管理调度器生命周期
class NotificationSchedulerContext:
    """通知调度器上下文管理器"""
    
    def __init__(self, db_session: Session, notification_service: NotificationService, 
                 config: NotificationConfig):
        self.scheduler = NotificationScheduler(db_session, notification_service, config)
    
    def __enter__(self):
        self.scheduler.start()
        return self.scheduler
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.scheduler.stop()
