import aio_pika
import json
import asyncio
import logging
from typing import Callable, Optional, Dict, Any, Union, Awaitable
from aio_pika import IncomingMessage

# 配置日志
logger = logging.getLogger(__name__)


class AsyncRabbitMQConsumer:
    """异步 RabbitMQ 消息消费者
    
    用于监听新钱包地址的更新通知，当收到新地址时自动添加到监控列表
    """
    
    def __init__(
        self, 
        host: str = 'localhost',
        port: int = 5672, 
        username: str = 'guest',
        password: str = 'guest',
        exchange_name: str = 'wallet_updates',
        exchange_type: str = 'fanout',
        queue_name: str = '',
        durable_queue: bool = False,
        auto_delete_queue: bool = True,
        exclusive_queue: bool = True,
        prefetch_count: int = 1
    ):
        """
        初始化异步 RabbitMQ 消费者

        Args:
            host: RabbitMQ 服务器地址
            port: RabbitMQ 端口
            username: 用户名
            password: 密码
            exchange_name: 交换机名称
            exchange_type: 交换机类型 ('fanout', 'topic', 'direct')
            queue_name: 队列名称，为空时自动生成
            durable_queue: 队列是否持久化
            auto_delete_queue: 是否自动删除队列
            exclusive_queue: 是否为独占队列
            prefetch_count: 预取消息数量
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.exchange_name = exchange_name
        self.exchange_type = exchange_type
        self.queue_name = queue_name
        self.durable_queue = durable_queue
        self.auto_delete_queue = auto_delete_queue
        self.exclusive_queue = exclusive_queue
        self.prefetch_count = prefetch_count
        
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self.queue: Optional[aio_pika.Queue] = None
        self.exchange: Optional[aio_pika.Exchange] = None
        self.consumer_tag: Optional[str] = None
        
        # 消息处理回调函数（支持同步和异步）
        self.message_handler: Optional[Union[Callable[[Dict[str, Any]], None], Callable[[Dict[str, Any]], Awaitable[None]]]] = None
        
        # 连接状态
        self.is_connected = False
        self.is_consuming = False

    async def connect(self) -> bool:
        """建立到 RabbitMQ 的连接"""
        try:
            # 创建连接
            connection_url = f"amqp://{self.username}:{self.password}@{self.host}:{self.port}/"
            self.connection = await aio_pika.connect_robust(
                connection_url,
                heartbeat=600
            )
            
            # 创建通道
            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=self.prefetch_count)
            
            # 声明交换机
            self.exchange = await self.channel.declare_exchange(
                self.exchange_name,
                self.exchange_type,
                durable=True
            )
            
            # 声明队列
            self.queue = await self.channel.declare_queue(
                self.queue_name,
                durable=self.durable_queue,
                auto_delete=self.auto_delete_queue,
                exclusive=self.exclusive_queue
            )
            
            # 绑定队列到交换机
            await self.queue.bind(self.exchange)
            
            self.is_connected = True
            logger.info(f"✅ 成功连接到 RabbitMQ: {self.host}:{self.port}")
            logger.info(f"📡 队列名称: {self.queue.name}")
            logger.info(f"🔄 交换机: {self.exchange_name} ({self.exchange_type})")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 连接到 RabbitMQ 失败: {e}")
            self.is_connected = False
            return False

    def set_message_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        """设置消息处理回调函数
        
        Args:
            handler: 消息处理函数，接收解析后的 JSON 消息
        """
        self.message_handler = handler
        logger.info("📝 消息处理器已设置")

    async def _process_message(self, message: IncomingMessage) -> None:
        """处理接收到的消息"""
        try:
            async with message.process():
                # 解析 JSON 消息
                message_body = message.body.decode('utf-8')
                message_data = json.loads(message_body)
                
                logger.info(f"📨 收到消息: {message_body}")
                
                # 验证消息格式
                if not self._validate_message(message_data):
                    logger.warning(f"⚠️ 消息格式无效: {message_data}")
                    return
                
                # 调用消息处理器
                if self.message_handler:
                    try:
                        await self._safe_call_handler(message_data)
                        logger.info(f"✅ 消息处理成功: {message_data.get('address', 'unknown')}")
                    except Exception as e:
                        logger.error(f"❌ 消息处理失败: {e}", exc_info=True)
                        raise  # 重新抛出异常，让消息被 NACK
                else:
                    logger.warning("⚠️ 未设置消息处理器")
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 解析失败: {e}")
            # JSON 格式错误，直接 ACK 避免重复处理
        except Exception as e:
            logger.error(f"❌ 处理消息时出错: {e}", exc_info=True)
            # 其他错误，让消息重新入队

    def _validate_message(self, message_data: Dict[str, Any]) -> bool:
        """验证消息格式"""
        if not isinstance(message_data, dict):
            return False
        
        # 检查必需的字段
        if 'address' not in message_data:
            return False
        
        address = message_data['address']
        if not isinstance(address, str) or not address:
            return False
        
        # 简单的以太坊地址格式验证
        if not (address.startswith('0x') and len(address) == 42):
            logger.warning(f"⚠️ 地址格式可能无效: {address}")
        
        return True

    async def _safe_call_handler(self, message_data: Dict[str, Any]) -> None:
        """安全调用消息处理器"""
        if asyncio.iscoroutinefunction(self.message_handler):
            await self.message_handler(message_data)
        else:
            self.message_handler(message_data)

    async def start_consuming(self) -> None:
        """开始消费消息"""
        if not self.is_connected:
            logger.error("❌ 未连接到 RabbitMQ，无法开始消费")
            return
        
        if self.is_consuming:
            logger.warning("⚠️ 已在消费消息中")
            return
        
        try:
            logger.info(f"🎧 开始监听队列: {self.queue.name}")
            
            # 开始消费消息
            await self.queue.consume(self._process_message)
            self.is_consuming = True
            
            logger.info("✅ 消息消费已启动")
            
        except Exception as e:
            logger.error(f"❌ 启动消息消费失败: {e}")
            self.is_consuming = False
            raise

    async def stop_consuming(self) -> None:
        """停止消费消息"""
        if not self.is_consuming:
            return
        
        try:
            if self.queue:
                await self.queue.cancel()
            
            self.is_consuming = False
            logger.info("⏹️ 消息消费已停止")
            
        except Exception as e:
            logger.error(f"❌ 停止消息消费失败: {e}")

    async def disconnect(self) -> None:
        """断开连接"""
        try:
            # 停止消费
            await self.stop_consuming()
            
            # 关闭连接
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
            
            self.is_connected = False
            logger.info("🔌 已断开 RabbitMQ 连接")
            
        except Exception as e:
            logger.error(f"❌ 断开连接失败: {e}")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.disconnect()

    def get_status(self) -> Dict[str, Any]:
        """获取消费者状态"""
        return {
            'connected': self.is_connected,
            'consuming': self.is_consuming,
            'host': self.host,
            'port': self.port,
            'exchange': self.exchange_name,
            'queue_name': self.queue.name if self.queue else None,
            'handler_set': self.message_handler is not None
        }


class WalletUpdateHandler:
    """钱包地址更新处理器
    
    专门用于处理钱包地址更新消息的处理类
    """
    
    def __init__(self, evm_monitor):
        """
        初始化钱包更新处理器
        
        Args:
            evm_monitor: EVM 监控器实例
        """
        self.evm_monitor = evm_monitor
        self.processed_count = 0
        
    async def handle_wallet_update(self, message_data: Dict[str, Any]) -> None:
        """处理钱包地址更新消息
        
        Args:
            message_data: 消息数据，格式: {"address": "0x..."}
        """
        try:
            address = message_data['address']
            
            # 添加到监控列表
            if hasattr(self.evm_monitor, 'add_watch_address'):
                self.evm_monitor.add_watch_address(address)
                self.processed_count += 1
                
                logger.info(f"🎯 新钱包地址已添加到监控: {address}")
                logger.info(f"📊 已处理钱包更新: {self.processed_count} 次")
            else:
                logger.error("❌ EVM 监控器不支持 add_watch_address 方法")
                
        except Exception as e:
            logger.error(f"❌ 处理钱包更新失败: {e}", exc_info=True)
            raise

    def get_stats(self) -> Dict[str, Any]:
        """获取处理统计信息"""
        return {
            'processed_count': self.processed_count,
            'monitor_strategy': getattr(self.evm_monitor.config, 'monitor_strategy', 'unknown'),
            'watch_addresses_count': len(getattr(self.evm_monitor.config, 'watch_addresses', []))
        }


# 使用示例
async def example_usage():
    """使用示例"""
    
    # 模拟 EVM 监控器
    class MockEVMMonitor:
        def __init__(self):
            self.watch_addresses = []
        
        def add_watch_address(self, address: str):
            if address not in self.watch_addresses:
                self.watch_addresses.append(address)
                print(f"添加监控地址: {address}")
    
    # 创建模拟监控器
    monitor = MockEVMMonitor()
    
    # 创建钱包更新处理器
    wallet_handler = WalletUpdateHandler(monitor)
    
    # 配置消费者
    consumer_config = {
        'host': 'localhost',
        'port': 5672,
        'username': 'guest',
        'password': 'guest',
        'exchange_name': 'wallet_updates',
        'exchange_type': 'fanout',
        'exclusive_queue': True,
        'prefetch_count': 1
    }
    
    # 使用异步上下文管理器
    async with AsyncRabbitMQConsumer(**consumer_config) as consumer:
        # 设置消息处理器
        consumer.set_message_handler(wallet_handler.handle_wallet_update)
        
        # 开始消费
        await consumer.start_consuming()
        
        # 等待消息（在实际应用中，这里会是无限循环）
        await asyncio.sleep(60)


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 运行示例
    asyncio.run(example_usage())
