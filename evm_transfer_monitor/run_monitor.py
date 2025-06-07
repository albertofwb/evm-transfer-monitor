"""
EVM 监控器启动脚本

支持数据库和通知服务的完整监控器
"""

import asyncio
import sys
import argparse
from typing import Optional

from config.monitor_config import MonitorConfig
from utils.token_parser import TokenParser
from utils.log_utils import get_logger
from core.evm_monitor import EVMMonitor, setup_signal_handlers

logger = get_logger(__name__)


async def run_monitor_with_services(chain_name: str = 'bsc', enable_notifications: bool = True) -> None:
    """
    运行带有完整服务的监控器
    
    Args:
        chain_name: 链名称
        enable_notifications: 是否启用通知服务
    """
    logger.info(f"🚀 启动 {chain_name.upper()} 链监控器（完整版）")
    
    try:
        # 创建配置
        config = MonitorConfig.from_chain_name(chain_name)
        logger.info(f"📋 链配置已加载: {config.rpc_url}")
        
        # 创建代币解析器
        token_parser = TokenParser(chain_name)
        logger.info(f"🪙 代币解析器已创建，支持代币: {list(token_parser.contracts.keys())}")
        
        # 自定义 RabbitMQ 配置（可选）
        rabbitmq_config = None
        if len(sys.argv) > 2 and sys.argv[2] == '--custom-rabbitmq':
            rabbitmq_config = {
                'enabled': True,
                'host': 'localhost',
                'port': 5672,
                'username': 'guest',
                'password': 'guest',
                'wallet_updates': {
                    'exchange_name': f'wallet_updates_{chain_name}',
                    'exchange_type': 'fanout',
                    'queue_name': f'monitor_queue_{chain_name}',
                    'durable_queue': False,
                    'auto_delete_queue': True,
                    'exclusive_queue': False,
                    'prefetch_count': 1
                }
            }
            logger.info("🐰 使用自定义 RabbitMQ 配置")
        
        # 创建监控器（传入链名称）
        monitor = EVMMonitor(
            config=config, 
            token_parser=token_parser, 
            chain_name=chain_name,
            rabbitmq_config=rabbitmq_config
        )
        
        # 设置信号处理器
        setup_signal_handlers(monitor)
        
        # 显示服务状态
        await _log_service_status(monitor)
        
        # 开始监控
        logger.info("🔄 开始主监控循环...")
        await monitor.start_monitoring()
        
    except KeyboardInterrupt:
        logger.info("⌨️ 接收到键盘中断")
    except Exception as e:
        logger.error(f"❌ 监控器运行失败: {e}", exc_info=True)
    finally:
        if 'monitor' in locals():
            await monitor.graceful_shutdown()


async def _log_service_status(monitor: EVMMonitor) -> None:
    """记录服务状态信息"""
    logger.info("📊 服务状态检查:")
    
    # 检查数据库状态
    if monitor.database_initializer:
        if monitor.database_initializer.is_connected():
            logger.info("   ✅ 数据库: 已连接")
            db_stats = monitor.database_initializer.get_stats()
            if 'pool_size' in db_stats:
                logger.info(f"   📊 连接池: {db_stats['checked_out']}/{db_stats['pool_size']} 使用中")
        else:
            logger.warning("   ⚠️ 数据库: 连接失败")
    else:
        logger.info("   🔇 数据库: 未启用")
    
    
    # 检查 RabbitMQ 状态
    if monitor.rabbitmq_enabled:
        logger.info("   🐰 RabbitMQ: 已启用")
    else:
        logger.info("   🔇 RabbitMQ: 未启用")


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='EVM 转账监控器（完整版）')
    parser.add_argument(
        'chain', 
        nargs='?', 
        default='bsc',
        help='要监控的链名称 (core, bsc, eth, polygon, arbitrum, optimism)'
    )
    parser.add_argument(
        '--disable-notifications',
        action='store_true',
        help='禁用通知服务'
    )
    parser.add_argument(
        '--custom-rabbitmq',
        action='store_true',
        help='使用自定义 RabbitMQ 配置'
    )
    parser.add_argument(
        '--health-check',
        action='store_true',
        help='只进行健康检查，不启动监控'
    )
    parser.add_argument(
        '--test-webhook',
        action='store_true',
        help='测试 Webhook 连接'
    )
    
    return parser.parse_args()


async def health_check(chain_name: str) -> None:
    """执行健康检查"""
    logger.info(f"🏥 对 {chain_name.upper()} 链进行健康检查...")
    
    try:
        # 创建配置和监控器
        config = MonitorConfig.from_chain_name(chain_name)
        token_parser = TokenParser(chain_name)
        monitor = EVMMonitor(config, token_parser, chain_name=chain_name)
        
        # 执行健康检查
        health_status = await monitor.get_health_status()
        
        # 显示结果
        logger.info("🏥 健康检查结果:")
        logger.info(f"   整体状态: {'✅ 健康' if health_status['overall_healthy'] else '❌ 不健康'}")
        logger.info(f"   RPC连接: {'✅' if health_status['rpc_healthy'] else '❌'}")
        logger.info(f"   数据库: {'✅' if health_status['database_healthy'] else '❌'}")
        logger.info(f"   通知服务: {'✅' if health_status['notification_healthy'] else '❌'}")
        logger.info(f"   RabbitMQ: {'✅' if health_status['rabbitmq_healthy'] else '❌'}")
        
        # 清理资源
        await monitor.graceful_shutdown()
        
        # 返回结果
        if not health_status['overall_healthy']:
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ 健康检查失败: {e}", exc_info=True)
        sys.exit(1)


async def test_webhook(chain_name: str) -> None:
    """测试 Webhook 连接"""
    logger.info(f"🔌 测试 {chain_name.upper()} 链的 Webhook 连接...")
    
    try:
        # 创建配置和监控器
        config = MonitorConfig.from_chain_name(chain_name)
        token_parser = TokenParser(chain_name)
        monitor = EVMMonitor(config, token_parser, chain_name=chain_name)
        
        # 等待初始化完成
        await asyncio.sleep(1)
        
        # 测试 Webhook
        if monitor.notification_enabled:
            result = await monitor.test_notification_webhook()
            if result:
                logger.info("✅ Webhook 测试成功")
            else:
                logger.error("❌ Webhook 测试失败")
                sys.exit(1)
        else:
            logger.warning("⚠️ 通知服务未启用")
        
        # 清理资源
        await monitor.graceful_shutdown()
        
    except Exception as e:
        logger.error(f"❌ Webhook 测试失败: {e}", exc_info=True)
        sys.exit(1)


async def main():
    """主函数"""
    args = parse_arguments()
    
    if args.health_check:
        await health_check(args.chain)
        return
    
    if args.test_webhook:
        await test_webhook(args.chain)
        return
    
    logger.info("=" * 60)
    logger.info("  EVM 转账监控器 - 完整版")
    logger.info("  支持数据库存储和通知服务")
    logger.info("=" * 60)
    
    await run_monitor_with_services(
        chain_name=args.chain,
        enable_notifications=not args.disable_notifications
    )


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常退出: {e}")
        sys.exit(1)
