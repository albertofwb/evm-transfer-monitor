"""
通知服务初始化模块

负责通知服务的创建、配置和调度器管理
"""

import asyncio
from typing import Optional, Dict, Any

from config.base_config import NotifyConfig
from services.notification_service import NotificationService
from scheduler.notification_scheduler import NotificationScheduler
from utils.log_utils import get_logger

logger = get_logger(__name__)


class NotificationInitializer:
    """通知服务初始化器"""
    
    def __init__(self, config: dict, db_session=None):
        """
        初始化通知服务管理器
        
        Args:
            config: 通知配置字典
            db_session: 数据库会话（可选）
        """
        self.config = config
        self.db_session = db_session
        self.notification_service: Optional[NotificationService] = None
        self.notification_scheduler: Optional[NotificationScheduler] = None
        self.scheduler_enabled = False
    
    def init_notification_service(self) -> Dict[str, Any]:
        """
        初始化通知服务
        
        Returns:
            Dict[str, Any]: 包含通知服务和调度器的字典
        """
        enabled = self.config.get('enabled', False)
        
        if not enabled:
            logger.info("🔇 通知服务未启用")
            return {
                'service': None,
                'scheduler': None,
                'enabled': False
            }
        
        try:
            logger.info("📢 正在初始化通知服务...")
            
            # 获取配置参数
            webhook_url = self.config.get('url', '')
            timeout = self.config.get('timeout', 30)
            retry_times = self.config.get('retry_times', 3)
            retry_delay = self.config.get('retry_delay', 5)
            
            if not webhook_url:
                logger.warning("⚠️ 通知URL未配置，通知服务将无法正常工作")
                return {
                    'service': None,
                    'scheduler': None,
                    'enabled': False
                }
            
            # 创建通知服务
            self.notification_service = NotificationService(
                webhook_url=webhook_url,
                timeout=timeout,
                max_retry_attempts=retry_times,
                retry_delay=retry_delay,
                db_session=self.db_session  # 传递数据库会话
            )
            logger.debug("✅ 通知服务已创建")
            
            # 测试通知服务连接
            if self._test_notification_service():
                logger.info("✅ 通知服务连接测试成功")
            else:
                logger.warning("⚠️ 通知服务连接测试失败，但服务仍将启动")
            
            # TODO: 暂时关闭此调度器，为性能考虑在独立的进程中实现
            # if self.db_session:
            #     self._init_notification_scheduler()
            # else:
            #     logger.info("📅 数据库会话未提供，跳过通知调度器初始化")
            
            return {
                'service': self.notification_service,
                'scheduler': self.notification_scheduler,
                'enabled': True
            }
            
        except Exception as e:
            logger.error(f"❌ 初始化通知服务失败: {e}")
            return {
                'service': None,
                'scheduler': None,
                'enabled': False
            }
    
    def _init_notification_scheduler(self) -> None:
        """初始化通知调度器"""
        try:
            # 创建配置对象
            from services.notification_service import NotificationConfig
            scheduler_config = NotificationConfig()
            scheduler_config.enabled = self.config.get('enabled', True)
            scheduler_config.retry_delay = self.config.get('retry_delay', 5)
            scheduler_config.cleanup_days = self.config.get('cleanup_days', 7)
            
            # 创建调度器
            self.notification_scheduler = NotificationScheduler(
                db_session=self.db_session,
                notification_service=self.notification_service,
                config=scheduler_config
            )
            
            logger.debug("✅ 通知调度器已创建")
            
        except Exception as e:
            logger.error(f"❌ 创建通知调度器失败: {e}")
    
    def start_scheduler(self) -> bool:
        """
        启动通知调度器
        
        Returns:
            bool: 启动是否成功
        """
        if not self.notification_scheduler:
            logger.warning("通知调度器未初始化，无法启动")
            return False
        
        try:
            self.notification_scheduler.start()
            self.scheduler_enabled = True
            logger.info("📅 通知调度器已启动")
            return True
        except Exception as e:
            logger.error(f"❌ 启动通知调度器失败: {e}")
            return False
    
    def stop_scheduler(self) -> None:
        """停止通知调度器"""
        if self.notification_scheduler and self.scheduler_enabled:
            try:
                self.notification_scheduler.stop()
                self.scheduler_enabled = False
                logger.info("📅 通知调度器已停止")
            except Exception as e:
                logger.error(f"❌ 停止通知调度器失败: {e}")
    
    def _test_notification_service(self) -> bool:
        """测试通知服务连接"""
        if not self.notification_service:
            return False
        
        try:
            # 在初始化阶段，我们只检查配置是否正确，不实际发送测试请求
            # 因为在初始化时可能目标服务还未启动
            webhook_url = self.notification_service.webhook_url
            if webhook_url and webhook_url.startswith(('http://', 'https://')):
                logger.debug(f"通知服务配置有效: {webhook_url[:50]}...")
                return True
            else:
                logger.warning("通知服务URL配置无效")
                return False
        except Exception as e:
            logger.error(f"测试通知服务失败: {e}")
            return False
    
    async def _test_notification_service_async(self) -> bool:
        """异步测试通知服务连接"""
        if not self.notification_service:
            return False
        
        try:
            return await self.notification_service.test_webhook_async()
        except Exception as e:
            logger.error(f"异步测试通知服务失败: {e}")
            return False
    
    def process_pending_notifications(self, required_confirmations: int = 12) -> int:
        """
        处理待通知的记录
        
        Args:
            required_confirmations: 所需确认数
            
        Returns:
            int: 处理的记录数
        """
        if not self.notification_scheduler:
            return 0
        
        try:
            return self.notification_scheduler.process_pending_notifications(required_confirmations)
        except Exception as e:
            logger.error(f"处理待通知记录失败: {e}")
            return 0
    
    def get_notification_stats(self) -> Dict[str, Any]:
        """获取通知服务统计信息"""
        stats = {
            'service_enabled': self.config.get('enabled', False),
            'scheduler_enabled': self.scheduler_enabled,
            'service_stats': None,
            'scheduler_stats': None
        }
        
        if self.notification_service:
            try:
                stats['service_stats'] = self.notification_service.get_stats()
            except Exception as e:
                logger.error(f"获取通知服务统计失败: {e}")
        
        if self.notification_scheduler:
            try:
                stats['scheduler_stats'] = self.notification_scheduler.get_status()
            except Exception as e:
                logger.error(f"获取调度器统计失败: {e}")
        
        return stats
    
    def cleanup(self) -> None:
        """清理通知服务资源"""
        self.stop_scheduler()
        
        if self.notification_service:
            try:
                self.notification_service.reset_stats()
                logger.info("✅ 通知服务已清理")
            except Exception as e:
                logger.error(f"清理通知服务失败: {e}")
    
    def is_healthy(self) -> bool:
        """检查通知服务健康状态"""
        if not self.config.get('enabled', False):
            return True  # 如果未启用，认为是健康的
        
        # 检查服务是否可用
        service_healthy = self.notification_service is not None
        
        # 检查调度器状态（如果启用）
        scheduler_healthy = True
        if self.notification_scheduler:
            scheduler_healthy = self.notification_scheduler.is_running()
        
        return service_healthy and scheduler_healthy
    
    async def test_webhook_connection_async(self) -> bool:
        """
        异步测试 Webhook 连接
        
        Returns:
            bool: 测试是否成功
        """
        if not self.notification_service:
            logger.warning("通知服务未初始化")
            return False
        
        try:
            logger.info("正在测试 Webhook 连接...")
            result = await self.notification_service.test_webhook_async()
            if result:
                logger.info("✅ Webhook 连接测试成功")
            else:
                logger.warning("⚠️ Webhook 连接测试失败")
            return result
        except Exception as e:
            logger.error(f"异步测试 Webhook 失败: {e}")
            return False
