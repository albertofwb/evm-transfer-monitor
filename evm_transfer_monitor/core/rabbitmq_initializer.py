"""
RabbitMQ管理器初始化模块

负责RabbitMQ消费者的创建、连接和管理
"""

from typing import Optional, Dict, Any

from managers.queue_manager import AsyncRabbitMQConsumer, WalletUpdateHandler
from utils.log_utils import get_logger

logger = get_logger(__name__)


class RabbitMQInitializer:
    """RabbitMQ初始化器"""
    
    def __init__(self, monitor_instance):
        """
        初始化RabbitMQ管理器
        
        Args:
            monitor_instance: 监控器实例
        """
        self.monitor = monitor_instance
        self.consumer: Optional[AsyncRabbitMQConsumer] = None
        self.handler: Optional[WalletUpdateHandler] = None
    
    async def init_rabbitmq_manager(self, rabbitmq_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        初始化RabbitMQ管理器
        
        Args:
            rabbitmq_config: RabbitMQ配置
            
        Returns:
            包含消费者和处理器的字典
        """
        rabbitmq_enabled = rabbitmq_config.get('enabled', False)
        
        if not rabbitmq_enabled:
            logger.info("🔇 RabbitMQ 未启用")
            return {'consumer': None, 'handler': None, 'enabled': False}
        
        try:
            logger.info("🐰 正在初始化RabbitMQ组件...")
            
            # 创建钱包更新处理器
            self.handler = WalletUpdateHandler(self.monitor)
            logger.debug("✅ 钱包更新处理器已创建")
            
            # 获取钱包更新配置
            wallet_config = rabbitmq_config.get('wallet_updates', {})
            
            # 创建消费者
            self.consumer = AsyncRabbitMQConsumer(
                host=rabbitmq_config.get('host', 'localhost'),
                port=rabbitmq_config.get('port', 5672),
                username=rabbitmq_config.get('username', 'guest'),
                password=rabbitmq_config.get('password', 'guest'),
                exchange_name=wallet_config.get('exchange_name', 'wallet_updates'),
                exchange_type=wallet_config.get('exchange_type', 'fanout'),
                queue_name=wallet_config.get('queue_name', ''),
                durable_queue=wallet_config.get('durable_queue', False),
                auto_delete_queue=wallet_config.get('auto_delete_queue', True),
                exclusive_queue=wallet_config.get('exclusive_queue', False),
                prefetch_count=wallet_config.get('prefetch_count', 1)
            )
            logger.debug("✅ RabbitMQ消费者已创建")
            
            # 连接并开始消费
            if await self.consumer.connect():
                self.consumer.set_message_handler(self.handler.handle_wallet_update)
                await self.consumer.start_consuming()
                logger.info("✅ RabbitMQ 消费者已启动")
                
                return {
                    'consumer': self.consumer,
                    'handler': self.handler,
                    'enabled': True
                }
            else:
                logger.warning("⚠️ RabbitMQ 连接失败")
                return {'consumer': None, 'handler': None, 'enabled': False}
                
        except Exception as e:
            logger.error(f"❌ 初始化 RabbitMQ 消费者失败: {e}")
            # RabbitMQ 失败不影响主程序运行
            return {'consumer': None, 'handler': None, 'enabled': False}
    
    async def cleanup(self) -> None:
        """清理RabbitMQ资源"""
        if self.consumer:
            try:
                await self.consumer.disconnect()
                logger.info("✅ RabbitMQ 消费者已关闭")
            except Exception as e:
                logger.error(f"❌ 关闭 RabbitMQ 消费者失败: {e}")
