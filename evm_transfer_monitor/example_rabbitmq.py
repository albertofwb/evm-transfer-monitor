"""
RabbitMQ 钱包地址更新系统使用示例

这个示例展示了如何使用 RabbitMQ 系统来接收和处理钱包地址更新通知
"""

import asyncio
import logging
from core.evm_monitor import EVMMonitor
from config.monitor_config import MonitorConfig
from utils.token_parser import TokenParser
from tests.test_rabbitmq_producer import AsyncRabbitMQProducer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def start_monitor_with_rabbitmq():
    """启动带有 RabbitMQ 支持的监控器"""
    logger.info("🚀 启动 EVM 监控器（支持 RabbitMQ 钱包地址更新）")
    
    # 创建配置
    config = MonitorConfig.from_chain_name('bsc')  # 使用 BSC 链
    config.set_strategy('watch_address')  # 设置为地址监控策略
    
    # 添加一些初始监控地址
    initial_addresses = [
        "0x1234567890abcdef1234567890abcdef12345678",
        "0xabcdef1234567890abcdef1234567890abcdef12"
    ]
    for addr in initial_addresses:
        config.add_watch_address(addr)
    
    # 创建代币解析器
    token_parser = TokenParser(config)
    
    # 创建监控器
    monitor = EVMMonitor(config, token_parser)
    
    try:
        # 启动监控（会自动初始化 RabbitMQ）
        await monitor.start_monitoring()
        
    except KeyboardInterrupt:
        logger.info("接收到中断信号")
    except Exception as e:
        logger.error(f"监控器运行失败: {e}", exc_info=True)
    finally:
        await monitor.graceful_shutdown()


async def send_test_messages():
    """发送测试钱包地址更新消息"""
    logger.info("📤 发送测试钱包地址更新消息")
    
    # 等待一些时间让监控器启动
    await asyncio.sleep(5)
    
    config = {
        'host': 'localhost',
        'port': 5672,
        'username': 'guest',
        'password': 'guest',
        'exchange_name': 'wallet_updates',
        'exchange_type': 'fanout'
    }
    
    test_addresses = [
        "0x9999999999999999999999999999999999999999",
        "0x8888888888888888888888888888888888888888",
        "0x7777777777777777777777777777777777777777"
    ]
    
    try:
        async with AsyncRabbitMQProducer(**config) as producer:
            for i, address in enumerate(test_addresses, 1):
                logger.info(f"📨 发送第 {i} 个测试地址: {address}")
                await producer.send_wallet_update(
                    address,
                    test_index=i,
                    timestamp=asyncio.get_event_loop().time()
                )
                await asyncio.sleep(2)  # 每2秒发送一个
                
    except Exception as e:
        logger.error(f"发送测试消息失败: {e}")


async def monitor_system_status(monitor):
    """监控系统状态"""
    logger.info("📊 开始监控系统状态")
    
    # 等待监控器启动
    await asyncio.sleep(3)
    
    while True:
        try:
            # 获取健康状态
            health_status = await monitor.get_health_status()
            
            logger.info("=" * 60)
            logger.info("📊 系统状态报告")
            logger.info(f"监控器运行: {health_status['is_running']}")
            logger.info(f"RPC 健康: {health_status['rpc_healthy']}")
            logger.info(f"当前区块: {health_status['current_block']}")
            logger.info(f"已处理区块: {health_status['blocks_processed']}")
            logger.info(f"待确认交易: {health_status['pending_transactions']}")
            logger.info(f"运行时间: {health_status['uptime_hours']:.2f} 小时")
            
            # RabbitMQ 状态
            if health_status['rabbitmq_enabled']:
                logger.info(f"RabbitMQ 健康: {health_status['rabbitmq_healthy']}")
                
                if 'rabbitmq_status' in health_status:
                    rabbitmq_status = health_status['rabbitmq_status']
                    consumer_status = rabbitmq_status.get('consumer_status', {})
                    handler_stats = rabbitmq_status.get('handler_stats', {})
                    
                    logger.info(f"RabbitMQ 连接: {consumer_status.get('connected', False)}")
                    logger.info(f"RabbitMQ 消费: {consumer_status.get('consuming', False)}")
                    logger.info(f"已处理消息: {handler_stats.get('processed_count', 0)}")
                    logger.info(f"监控地址数: {handler_stats.get('watch_addresses_count', 0)}")
            else:
                logger.info("RabbitMQ: 未启用")
            
            logger.info("=" * 60)
            
            # 每30秒检查一次
            await asyncio.sleep(30)
            
        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            await asyncio.sleep(10)


async def demo_concurrent_operations():
    """演示并发操作"""
    logger.info("🎭 演示并发操作：监控器 + 消息发送 + 状态监控")
    
    # 创建配置
    config = MonitorConfig.from_chain_name('bsc')
    config.set_strategy('watch_address')
    
    # 添加初始地址
    config.add_watch_address("0x1111111111111111111111111111111111111111")
    
    # 创建监控器
    token_parser = TokenParser(config)
    monitor = EVMMonitor(config, token_parser)
    
    # 并发运行多个任务
    tasks = [
        asyncio.create_task(start_monitor_with_rabbitmq()),
        asyncio.create_task(send_test_messages()),
        asyncio.create_task(monitor_system_status(monitor))
    ]
    
    try:
        # 等待任意一个任务完成或失败
        done, pending = await asyncio.wait(
            tasks, 
            return_when=asyncio.FIRST_EXCEPTION
        )
        
        # 取消剩余任务
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
                
    except Exception as e:
        logger.error(f"演示过程中出错: {e}")


async def simple_test():
    """简单测试"""
    logger.info("🧪 运行简单测试")
    
    # 只启动监控器，等待 RabbitMQ 消息
    await start_monitor_with_rabbitmq()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        
        if mode == "monitor":
            # 只启动监控器
            asyncio.run(simple_test())
        elif mode == "send":
            # 只发送消息
            asyncio.run(send_test_messages())
        elif mode == "demo":
            # 完整演示
            asyncio.run(demo_concurrent_operations())
        else:
            print("可用模式:")
            print("  monitor - 只启动监控器")
            print("  send    - 只发送测试消息")
            print("  demo    - 完整演示")
    else:
        # 默认运行完整演示
        asyncio.run(demo_concurrent_operations())
