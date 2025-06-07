"""
RabbitMQ 消息发送器测试工具

用于测试钱包地址更新通知功能，发送测试消息到 RabbitMQ 队列
"""

import aio_pika
import json
import asyncio
import logging
from typing import List, Dict, Any
from aio_pika import ExchangeType

logger = logging.getLogger(__name__)


class AsyncRabbitMQProducer:
    """异步 RabbitMQ 消息生产者
    
    用于发送钱包地址更新通知的测试消息
    """
    
    def __init__(
        self,
        host: str = 'localhost',
        port: int = 5672,
        username: str = 'guest',
        password: str = 'guest',
        virtual_host: str = '/',
        exchange_name: str = 'wallet_updates',
        exchange_type: str = 'fanout',
        heartbeat: int = 600,
        connection_timeout: int = 30
    ):
        """
        初始化消息生产者
        
        Args:
            host: RabbitMQ 服务器地址
            port: RabbitMQ 端口
            username: 用户名
            password: 密码
            virtual_host: 虚拟主机
            exchange_name: 交换机名称
            exchange_type: 交换机类型
            heartbeat: 心跳间隔（秒）
            connection_timeout: 连接超时（秒）
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.virtual_host = virtual_host
        self.exchange_name = exchange_name
        self.exchange_type = exchange_type
        self.heartbeat = heartbeat
        self.connection_timeout = connection_timeout
        
        self.connection = None
        self.channel = None
        self.exchange = None
        self._is_connected = False

    async def connect(self) -> bool:
        """连接到 RabbitMQ"""
        try:
            # 构建连接URL
            connection_url = (
                f"amqp://{self.username}:{self.password}@"
                f"{self.host}:{self.port}{self.virtual_host}"
            )
            
            # 创建连接
            logger.info(f"🔌 正在连接到 RabbitMQ: {self.host}:{self.port}")
            self.connection = await aio_pika.connect_robust(
                connection_url,
                heartbeat=self.heartbeat,
                connection_timeout=self.connection_timeout
            )
            
            # 创建通道
            self.channel = await self.connection.channel()
            
            # 声明交换机
            exchange_type_enum = getattr(ExchangeType, self.exchange_type.upper())
            self.exchange = await self.channel.declare_exchange(
                self.exchange_name,
                exchange_type_enum,
                durable=True
            )
            
            self._is_connected = True
            logger.info(f"✅ 成功连接到 RabbitMQ: {self.host}:{self.port}")
            logger.info(f"🔄 交换机: {self.exchange_name} ({self.exchange_type})")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 连接到 RabbitMQ 失败: {e}")
            self._is_connected = False
            return False

    async def send_wallet_update(self, address: str, **extra_data) -> bool:
        """发送钱包地址更新消息
        
        Args:
            address: 钱包地址
            **extra_data: 额外数据
            
        Returns:
            是否发送成功
        """
        if not self._is_connected:
            logger.error("❌ 未连接到 RabbitMQ")
            return False
        
        try:
            # 构造消息
            message_data = {
                "address": address,
                **extra_data
            }
            
            # 序列化消息
            message_body = json.dumps(message_data, ensure_ascii=False)
            
            # 发送消息
            await self.exchange.publish(
                aio_pika.Message(
                    message_body.encode('utf-8'),
                    content_type='application/json'
                ),
                routing_key=''  # fanout 交换机不需要路由键
            )
            
            logger.info(f"📤 已发送钱包更新消息: {address}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 发送消息失败: {e}")
            return False

    async def send_batch_wallet_updates(self, addresses: List[str], delay: float = 1.0) -> int:
        """批量发送钱包地址更新消息
        
        Args:
            addresses: 钱包地址列表
            delay: 发送间隔（秒）
            
        Returns:
            成功发送的消息数量
        """
        success_count = 0
        
        for i, address in enumerate(addresses, 1):
            if await self.send_wallet_update(address, batch_index=i, total=len(addresses)):
                success_count += 1
            
            # 控制发送频率
            if delay > 0 and i < len(addresses):
                await asyncio.sleep(delay)
        
        logger.info(f"📊 批量发送完成: {success_count}/{len(addresses)} 成功")
        return success_count

    async def disconnect(self) -> None:
        """断开连接"""
        try:
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
            
            self._is_connected = False
            logger.info("🔌 已断开 RabbitMQ 连接")
            
        except Exception as e:
            logger.error(f"❌ 断开连接失败: {e}")

    async def __aenter__(self) -> 'AsyncRabbitMQProducer':
        """异步上下文管理器入口"""
        if not await self.connect():
            raise RuntimeError("无法连接到 RabbitMQ")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.disconnect()


def generate_test_addresses(count: int = 10) -> List[str]:
    """生成测试用的钱包地址
    
    Args:
        count: 生成数量
        
    Returns:
        钱包地址列表
    """
    import random
    
    addresses = []
    for i in range(count):
        # 生成随机的40位十六进制字符串
        hex_part = ''.join([random.choice('0123456789abcdef') for _ in range(40)])
        address = f"0x{hex_part}"
        addresses.append(address)
    
    return addresses


async def test_single_message():
    """测试发送单个消息"""
    logger.info("🧪 测试发送单个钱包更新消息")
    
    config = {
        'host': 'localhost',
        'port': 5672,
        'username': 'guest',
        'password': 'guest',
        'virtual_host': '/',
        'exchange_name': 'wallet_updates',
        'exchange_type': 'fanout'
    }
    
    async with AsyncRabbitMQProducer(**config) as producer:
        test_address = "0x1234567890abcdef1234567890abcdef12345678"
        success = await producer.send_wallet_update(
            test_address,
            timestamp=asyncio.get_event_loop().time(),
            test_type="single_message"
        )
        
        if success:
            logger.info("✅ 单个消息测试成功")
        else:
            logger.error("❌ 单个消息测试失败")


async def test_batch_messages():
    """测试批量发送消息"""
    logger.info("🧪 测试批量发送钱包更新消息")
    
    config = {
        'host': 'localhost',
        'port': 5672,
        'username': 'guest',
        'password': 'guest',
        'virtual_host': '/',
        'exchange_name': 'wallet_updates',
        'exchange_type': 'fanout'
    }
    
    # 生成测试地址
    test_addresses = generate_test_addresses(5)
    logger.info(f"📝 生成了 {len(test_addresses)} 个测试地址")
    
    async with AsyncRabbitMQProducer(**config) as producer:
        success_count = await producer.send_batch_wallet_updates(
            test_addresses,
            delay=0.5  # 每0.5秒发送一个
        )
        
        if success_count == len(test_addresses):
            logger.info("✅ 批量消息测试成功")
        else:
            logger.error(f"❌ 批量消息测试部分失败: {success_count}/{len(test_addresses)}")


async def send_wallet_update_to_chain(
    chain_name: str,
    address: str,
    host: str = 'localhost',
    port: int = 5672,
    username: str = 'guest',
    password: str = 'guest'
) -> bool:
    """发送钱包地址更新消息到指定链
    
    Args:
        chain_name: 链名称
        address: 钱包地址
        host: RabbitMQ 主机
        port: RabbitMQ 端口
        username: 用户名
        password: 密码
        
    Returns:
        是否发送成功
    """
    # 根据链名称生成交换机名称
    exchange_name = f"wallet_updates_{chain_name}"
    
    config = {
        'host': host,
        'port': port,
        'username': username,
        'password': password,
        'exchange_name': exchange_name,
        'exchange_type': 'fanout'
    }
    
    try:
        async with AsyncRabbitMQProducer(**config) as producer:
            success = await producer.send_wallet_update(
                address,
                chain=chain_name,
                timestamp=asyncio.get_event_loop().time()
            )
            
            if success:
                logger.info(f"✅ 已发送到 {chain_name} 链: {address}")
            else:
                logger.error(f"❌ 发送失败 {chain_name} 链: {address}")
                
            return success
            
    except Exception as e:
        logger.error(f"❌ 发送消息到 {chain_name} 链失败: {e}")
        return False


async def test_multi_chain_messages():
    """测试多链消息发送"""
    logger.info("🌍 测试多链钱包地址更新消息")
    
    # 测试数据
    test_data = {
        'bsc': [
            "0x1111111111111111111111111111111111111111",
            "0x2222222222222222222222222222222222222222"
        ],
        'ethereum': [
            "0x3333333333333333333333333333333333333333",
            "0x4444444444444444444444444444444444444444"
        ],
        'polygon': [
            "0x5555555555555555555555555555555555555555",
            "0x6666666666666666666666666666666666666666"
        ]
    }
    
    # 对每个链发送测试消息
    for chain_name, addresses in test_data.items():
        logger.info(f"📬 发送 {chain_name.upper()} 链测试消息")
        
        for address in addresses:
            success = await send_wallet_update_to_chain(chain_name, address)
            await asyncio.sleep(1)  # 间隔发送
        
        logger.info(f"✅ {chain_name.upper()} 链测试消息发送完成")
        await asyncio.sleep(2)


async def interactive_test():
    """交互式测试"""
    logger.info("🎮 进入交互式测试模式")
    
    config = {
        'host': 'localhost',
        'port': 5672,
        'username': 'guest',
        'password': 'guest',
        'virtual_host': '/',
        'exchange_name': 'wallet_updates',
        'exchange_type': 'fanout'
    }
    
    async with AsyncRabbitMQProducer(**config) as producer:
        logger.info("请输入钱包地址（输入 'quit' 退出）：")
        
        while True:
            try:
                # 在实际环境中，这里应该使用 aioconsole 或其他异步输入方法
                # 这里为了简化，使用同步输入
                address = input("地址: ").strip()
                
                if address.lower() == 'quit':
                    break
                
                if address:
                    success = await producer.send_wallet_update(
                        address,
                        timestamp=asyncio.get_event_loop().time(),
                        test_type="interactive"
                    )
                    
                    if success:
                        logger.info(f"✅ 已发送: {address}")
                    else:
                        logger.error(f"❌ 发送失败: {address}")
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"输入处理错误: {e}")
    
    logger.info("🔙 退出交互式测试")


async def run_all_tests():
    """运行所有测试"""
    logger.info("🚀 开始运行所有 RabbitMQ 测试")
    
    try:
        # 测试单个消息
        await test_single_message()
        await asyncio.sleep(1)
        
        # 测试批量消息
        await test_batch_messages()
        await asyncio.sleep(1)
        
        # 测试无效消息
        await test_invalid_message()
        await asyncio.sleep(1)
        
        logger.info("🎉 所有测试完成")
        
    except Exception as e:
        logger.error(f"❌ 测试过程中出错: {e}")


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 选择测试模式
    import sys
    
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        
        if mode == "single":
            asyncio.run(test_single_message())
        elif mode == "batch":
            asyncio.run(test_batch_messages())
        elif mode == "invalid":
            asyncio.run(test_invalid_message())
        elif mode == "interactive":
            asyncio.run(interactive_test())
        else:
            print("可用模式: single, batch, invalid, interactive")
    else:
        # 运行所有测试
        asyncio.run(run_all_tests())
