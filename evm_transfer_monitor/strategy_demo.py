"""
监控策略示例

演示如何使用两种不同的监控策略：
1. 大额交易监控 - 监控超过阈值的交易
2. 指定地址监控 - 监控特定地址的收款
"""

import asyncio
from config.monitor_config import MonitorConfig, MonitorStrategy
from core.evm_monitor import EVMMonitor
from utils.log_utils import get_logger

logger = get_logger(__name__)


async def demo_large_amount_strategy():
    """演示大额交易监控策略"""
    logger.info("=" * 60)
    logger.info("🎯 演示：大额交易监控策略")
    logger.info("=" * 60)
    
    # 创建配置，默认为大额交易策略
    config = MonitorConfig()
    config.set_strategy(MonitorStrategy.LARGE_AMOUNT)
    
    # 创建监控器
    monitor = EVMMonitor(config)
    
    # 显示当前配置
    logger.info(f"📋 当前策略: {config.get_strategy_description()}")
    
    # 演示动态调整阈值
    logger.info("\n🔧 演示动态调整阈值:")
    monitor.update_thresholds(ETH=0.5, USDT=5000.0, USDC=5000.0)
    
    logger.info("💡 在此策略下，系统会监控所有超过阈值的交易")
    logger.info("📊 优点：能发现网络中的大额转移")
    logger.info("⚠️ 注意：可能会产生大量日志")
    
    return monitor


async def demo_watch_address_strategy():
    """演示指定地址监控策略"""
    logger.info("=" * 60)
    logger.info("🎯 演示：指定地址监控策略")
    logger.info("=" * 60)
    
    # 创建配置
    config = MonitorConfig()
    config.set_strategy(MonitorStrategy.WATCH_ADDRESS)
    
    # 创建监控器
    monitor = EVMMonitor(config)
    
    # 显示当前配置
    logger.info(f"📋 当前策略: {config.get_strategy_description()}")
    
    # 演示添加监控地址
    logger.info("\n🔧 演示地址管理:")
    example_addresses = [
        "0x1234567890123456789012345678901234567890",
        "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
    ]
    
    for addr in example_addresses:
        monitor.add_watch_address(addr)
    
    # 演示移除地址
    if len(config.watch_addresses) > 2:
        remove_addr = config.watch_addresses[-1]
        monitor.remove_watch_address(remove_addr)
    
    logger.info("💡 在此策略下，系统只监控发送到指定地址的交易")
    logger.info("📊 优点：精确监控，减少噪音")
    logger.info("⚠️ 注意：需要预先知道要监控的地址")
    
    return monitor


async def demo_strategy_switching():
    """演示策略切换"""
    logger.info("=" * 60)
    logger.info("🔄 演示：动态策略切换")
    logger.info("=" * 60)
    
    # 创建监控器
    config = MonitorConfig()
    monitor = EVMMonitor(config)
    
    # 初始策略
    logger.info(f"📋 初始策略: {config.get_strategy_description()}")
    
    # 切换到地址监控策略
    logger.info("\n🔧 切换到地址监控策略:")
    monitor.set_monitor_strategy("watch_address")
    
    # 添加一些地址
    monitor.add_watch_address("0x1111111111111111111111111111111111111111")
    
    # 切换回大额交易策略
    logger.info("\n🔧 切换回大额交易策略:")
    monitor.set_monitor_strategy("large_amount")
    
    # 尝试设置阈值
    monitor.update_thresholds(ETH=2.0)
    
    # 再次切换到地址监控并尝试设置阈值（应该警告）
    logger.info("\n🔧 切换到地址监控后尝试设置阈值:")
    monitor.set_monitor_strategy("watch_address")
    monitor.update_thresholds(ETH=1.0)  # 这会产生警告
    
    return monitor


async def main():
    """主函数"""
    logger.info("🚀 监控策略演示程序启动")
    
    try:
        # 演示大额交易策略
        large_amount_monitor = await demo_large_amount_strategy()
        
        await asyncio.sleep(2)  # 暂停一下
        
        # 演示地址监控策略
        watch_address_monitor = await demo_watch_address_strategy()
        
        await asyncio.sleep(2)  # 暂停一下
        
        # 演示策略切换
        switching_monitor = await demo_strategy_switching()
        
        logger.info("\n" + "=" * 60)
        logger.info("📝 总结")
        logger.info("=" * 60)
        logger.info("✅ 大额交易策略：适合监控网络中的大额资金流动")
        logger.info("✅ 地址监控策略：适合监控特定钱包的收款情况")
        logger.info("✅ 支持运行时动态切换策略")
        logger.info("✅ 每种策略都有独立的配置管理方法")
        
        logger.info("\n💡 使用建议：")
        logger.info("   - 交易所/DeFi监控 → 使用大额交易策略")
        logger.info("   - 个人钱包监控 → 使用地址监控策略")
        logger.info("   - 合规监控 → 根据需求灵活切换")
        
        # 选择一个策略开始实际监控
        logger.info("\n🎯 选择地址监控策略开始实际监控...")
        logger.info("提示：按 Ctrl+C 可以优雅退出")
        
        # 使用地址监控策略
        switching_monitor.set_monitor_strategy("watch_address")
        
        # 开始监控（这里只是演示，实际使用时会进入监控循环）
        # await switching_monitor.start_monitoring()
        
        logger.info("演示完成！如需实际监控，请取消注释上面的 start_monitoring() 调用")
        
    except Exception as e:
        logger.error(f"演示过程中发生错误: {e}", exc_info=True)


if __name__ == '__main__':
    asyncio.run(main())
