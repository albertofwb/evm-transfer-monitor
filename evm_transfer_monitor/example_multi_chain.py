"""
多链 EVM 监控器部署示例

演示如何同时启动多个链的监控器，每个都有独立的 RabbitMQ 配置
"""

import asyncio
import logging
from typing import List, Dict, Any
from core.evm_monitor import EVMMonitor
from config.monitor_config import MonitorConfig
from utils.token_parser import TokenParser
from config.base_config import get_rabbitmq_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


class MultiChainMonitor:
    """多链监控器管理器"""
    
    def __init__(self):
        self.monitors: Dict[str, EVMMonitor] = {}
        self.running = False
        
    async def add_chain_monitor(
        self, 
        chain_name: str, 
        custom_rabbitmq_config: Dict[str, Any] = None
    ) -> None:
        """添加链监控器
        
        Args:
            chain_name: 链名称
            custom_rabbitmq_config: 自定义 RabbitMQ 配置
        """
        if chain_name in self.monitors:
            logger.warning(f"⚠️ {chain_name} 链监控器已存在")
            return
        
        try:
            # 创建配置
            config = MonitorConfig.from_chain_name(chain_name)
            config.set_strategy('watch_address')  # 设置为地址监控策略
            
            # 创建代币解析器
            token_parser = TokenParser(config)
            
            # 创建监控器（每个链有独立的配置）
            monitor = EVMMonitor(
                config, 
                token_parser, 
                chain_name=chain_name,
                rabbitmq_config=custom_rabbitmq_config
            )
            
            self.monitors[chain_name] = monitor
            logger.info(f"✅ {chain_name} 链监控器已添加")
            
        except Exception as e:
            logger.error(f"❌ 添加 {chain_name} 链监控器失败: {e}")
    
    async def start_all_monitors(self) -> None:
        """启动所有链监控器"""
        if not self.monitors:
            logger.error("❌ 没有可启动的监控器")
            return
        
        self.running = True
        
        # 创建所有监控器的启动任务
        tasks = []
        for chain_name, monitor in self.monitors.items():
            task = asyncio.create_task(
                self._run_single_monitor(chain_name, monitor),
                name=f"monitor_{chain_name}"
            )
            tasks.append(task)
        
        logger.info(f"🚀 启动 {len(tasks)} 个链监控器")
        
        try:
            # 等待所有监控器运行
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"❌ 多链监控运行失败: {e}")
        finally:
            self.running = False
    
    async def _run_single_monitor(self, chain_name: str, monitor: EVMMonitor) -> None:
        """运行单个监控器"""
        try:
            logger.info(f"🏁 启动 {chain_name} 链监控器")
            await monitor.start_monitoring()
        except Exception as e:
            logger.error(f"❌ {chain_name} 链监控器运行失败: {e}")
        finally:
            logger.info(f"🛑 {chain_name} 链监控器已停止")
    
    async def stop_all_monitors(self) -> None:
        """停止所有监控器"""
        if not self.running:
            return
        
        logger.info("🛑 正在停止所有链监控器...")
        
        # 优雅关闭所有监控器
        shutdown_tasks = []
        for chain_name, monitor in self.monitors.items():
            task = asyncio.create_task(
                monitor.graceful_shutdown(),
                name=f"shutdown_{chain_name}"
            )
            shutdown_tasks.append(task)
        
        try:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)
            logger.info("✅ 所有链监控器已停止")
        except Exception as e:
            logger.error(f"❌ 停止监控器时出错: {e}")
        
        self.running = False
    
    async def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有链的状态"""
        status_dict = {}
        
        for chain_name, monitor in self.monitors.items():
            try:
                status = await monitor.get_health_status()
                status_dict[chain_name] = status
            except Exception as e:
                status_dict[chain_name] = {'error': str(e)}
        
        return status_dict


async def setup_multi_chain_monitors() -> MultiChainMonitor:
    """设置多链监控器"""
    multi_monitor = MultiChainMonitor()
    
    # 获取基础 RabbitMQ 配置
    base_rabbitmq_config = get_rabbitmq_config()
    
    # 定义要监控的链及其配置
    chain_configs = {
        'bsc': {
            **base_rabbitmq_config,
            'wallet_updates': {
                **base_rabbitmq_config['wallet_updates'],
                'exchange_name': 'wallet_updates',  # 基础名称，会自动加上链名称
            }
        },
        'ethereum': {
            **base_rabbitmq_config,
            'wallet_updates': {
                **base_rabbitmq_config['wallet_updates'],
                'exchange_name': 'wallet_updates',
            }
        },
        'polygon': {
            **base_rabbitmq_config,
            'wallet_updates': {
                **base_rabbitmq_config['wallet_updates'],
                'exchange_name': 'wallet_updates',
            }
        },
        'arbitrum': {
            **base_rabbitmq_config,
            'wallet_updates': {
                **base_rabbitmq_config['wallet_updates'],
                'exchange_name': 'wallet_updates',
            }
        }
    }
    
    # 添加每个链的监控器
    for chain_name, rabbitmq_config in chain_configs.items():
        await multi_monitor.add_chain_monitor(chain_name, rabbitmq_config)
    
    return multi_monitor


async def status_monitor(multi_monitor: MultiChainMonitor):
    """状态监控任务"""
    await asyncio.sleep(10)  # 等待监控器启动
    
    while multi_monitor.running:
        try:
            logger.info("=" * 80)
            logger.info("📊 多链监控状态报告")
            
            all_status = await multi_monitor.get_all_status()
            
            for chain_name, status in all_status.items():
                if 'error' in status:
                    logger.error(f"{chain_name.upper()}: ❌ {status['error']}")
                else:
                    health = "✅" if status.get('overall_healthy', False) else "❌"
                    rabbitmq = "🟢" if status.get('rabbitmq_healthy', False) else "🔴"
                    
                    logger.info(f"{chain_name.upper()}: {health} 运行:{status.get('is_running', False)} | RMQ:{rabbitmq} | 区块:{status.get('current_block', 0)} | 待确认:{status.get('pending_transactions', 0)}")
                    
                    # RabbitMQ 详细信息
                    if status.get('rabbitmq_status'):
                        rmq_status = status['rabbitmq_status']
                        consumer_status = rmq_status.get('consumer_status', {})
                        handler_stats = rmq_status.get('handler_stats', {})
                        
                        logger.info(f"  📬 RabbitMQ: 连接:{consumer_status.get('connected', False)} | 消费:{consumer_status.get('consuming', False)} | 已处理:{handler_stats.get('processed_count', 0)}")
            
            logger.info("=" * 80)
            await asyncio.sleep(30)  # 每30秒检查一次
            
        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            await asyncio.sleep(10)


async def demo_multi_chain():
    """演示多链监控"""
    logger.info("🌍 开始多链 EVM 监控演示")
    
    # 设置多链监控器
    multi_monitor = await setup_multi_chain_monitors()
    
    # 创建任务
    monitor_task = asyncio.create_task(
        multi_monitor.start_all_monitors(),
        name="multi_chain_monitors"
    )
    
    status_task = asyncio.create_task(
        status_monitor(multi_monitor),
        name="status_monitor"
    )
    
    try:
        # 等待任意一个任务完成
        done, pending = await asyncio.wait(
            [monitor_task, status_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # 取消剩余任务
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
                
    except KeyboardInterrupt:
        logger.info("🚨 接收到中断信号")
    except Exception as e:
        logger.error(f"❗️ 多链监控异常: {e}")
    finally:
        await multi_monitor.stop_all_monitors()


async def demo_single_chain_custom_config():
    """演示单链自定义配置"""
    logger.info("🔗 开始单链自定义配置演示")
    
    # 自定义 RabbitMQ 配置
    custom_rabbitmq_config = {
        'enabled': True,
        'host': 'localhost',
        'port': 5672,
        'username': 'guest',
        'password': 'guest',
        'virtual_host': '/',
        'heartbeat': 600,
        'connection_timeout': 30,
        'wallet_updates': {
            'exchange_name': 'custom_wallet_updates',  # 自定义交换机名称
            'exchange_type': 'topic',  # 使用 topic 类型
            'queue_name': 'custom_queue',  # 指定队列名称
            'durable_queue': True,  # 持久化队列
            'auto_delete_queue': False,
            'exclusive_queue': False,
            'prefetch_count': 5
        },
        'reconnect': {
            'max_retries': 3,
            'retry_delay': 10,
            'backoff_multiplier': 1.5
        }
    }
    
    # 创建配置
    config = MonitorConfig.from_chain_name('bsc')
    config.set_strategy('watch_address')
    
    # 添加一些测试地址
    test_addresses = [
        "0x1111111111111111111111111111111111111111",
        "0x2222222222222222222222222222222222222222"
    ]
    for addr in test_addresses:
        config.add_watch_address(addr)
    
    # 创建代币解析器
    token_parser = TokenParser(config)
    
    # 创建监控器（使用自定义配置）
    monitor = EVMMonitor(
        config, 
        token_parser, 
        chain_name='bsc_custom',
        rabbitmq_config=custom_rabbitmq_config
    )
    
    try:
        await monitor.start_monitoring()
    except KeyboardInterrupt:
        logger.info("接收到中断信号")
    except Exception as e:
        logger.error(f"监控器运行失败: {e}")
    finally:
        await monitor.graceful_shutdown()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        
        if mode == "multi":
            # 多链演示
            asyncio.run(demo_multi_chain())
        elif mode == "custom":
            # 自定义配置演示
            asyncio.run(demo_single_chain_custom_config())
        else:
            print("可用模式:")
            print("  multi  - 多链监控演示")
            print("  custom - 自定义配置演示")
    else:
        # 默认运行多链演示
        asyncio.run(demo_multi_chain())
