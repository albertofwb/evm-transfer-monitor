"""
主监控器类

协调各个组件，提供统一的监控接口和控制逻辑
支持两种监控策略：大额交易监控 和 指定地址监控
"""

import asyncio
import signal
import time
from typing import Optional, Dict, Any

from web3.exceptions import BlockNotFound

from config.monitor_config import MonitorConfig, MonitorStrategy
from models.data_types import MonitorStatus
from utils.token_parser import TokenParser
from utils.log_utils import get_logger

# 导入新的初始化模块
from core.monitor_initializer import MonitorInitializer
from core.network_validator import NetworkValidator
from core.rabbitmq_initializer import RabbitMQInitializer
from core.startup_logger import StartupLogger

logger = get_logger(__name__)


class EVMMonitor:
    """主监控器类 - 协调各个组件"""
    
    def __init__(
        self, 
        config: MonitorConfig, 
        token_parser: TokenParser, 
        chain_name: Optional[str] = None,
        rabbitmq_config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化监控器
        
        Args:
            config: 监控配置
            token_parser: 代币解析器
            chain_name: 链名称（用于区分不同的实例）
            rabbitmq_config: RabbitMQ 配置（如果不提供则使用默认配置）
        """
        self.config = config    
        self.token_parser = token_parser
        self.chain_name = chain_name or getattr(config, 'chain_name', 'unknown')
        self.is_running = False
        self.last_block = 0
        
        # 创建初始化器
        self.initializer = MonitorInitializer(self.config, self.token_parser, self.chain_name)
        
        # 初始化核心组件
        components = self.initializer.init_core_components()
        self.rpc_manager = components['rpc_manager']
        self.tx_processor = components['tx_processor']
        self.confirmation_manager = components['confirmation_manager']
        self.stats_reporter = components['stats_reporter']
        
        # 初始化数据库和通知服务
        db_notification_components = self.initializer.init_database_and_notification()
        self.database_initializer = db_notification_components['database_initializer']
        self.db_session = db_notification_components['db_session']
        self.notification_initializer = db_notification_components['notification_initializer']
        self.notification_service = db_notification_components['notification_service']
        # self.notification_scheduler = db_notification_components['notification_scheduler']
        self.notification_enabled = db_notification_components['notification_enabled']
        self.scheduler_started = db_notification_components['scheduler_started']
        
        # 初始化RabbitMQ配置
        self.rabbitmq_config = self.initializer.init_rabbitmq_config(rabbitmq_config)
        self.rabbitmq_enabled = self.rabbitmq_config.get('enabled', False)
        
        # 为当前实例定制RabbitMQ配置
        if self.rabbitmq_enabled:
            self.rabbitmq_config = self.initializer.customize_rabbitmq_config(self.rabbitmq_config)
        
        # RabbitMQ相关组件（延迟初始化）
        self.rabbitmq_initializer = RabbitMQInitializer(self)
        self.rabbitmq_consumer = None
        self.wallet_handler = None
        
        # 其他组件
        self.network_validator = NetworkValidator(self.rpc_manager, self.token_parser)
        self.startup_logger = StartupLogger(self.config)
    
    async def start_monitoring(self) -> None:
        """开始监控"""
        if self.is_running:
            logger.warning("监控器已在运行中")
            return
        
        self.is_running = True
        
        try:
            # 检查网络连接
            await self.network_validator.check_network_connection()
            
            # 初始化RabbitMQ管理器
            rabbitmq_components = await self.rabbitmq_initializer.init_rabbitmq_manager(self.rabbitmq_config)
            self.rabbitmq_consumer = rabbitmq_components['consumer']
            self.wallet_handler = rabbitmq_components['handler']
            
            # 显示启动信息
            self.startup_logger.log_startup_info()
            
            # 获取起始区块
            self.last_block = await self.rpc_manager.get_cached_block_number()
            
            # 主监控循环
            await self._monitoring_loop()
            
        except Exception as e:
            logger.error(f"监控启动失败: {e}", exc_info=True)
            self.is_running = False
            raise
    
    async def _monitoring_loop(self) -> None:
        """主监控循环"""
        logger.info("🔄 开始监控循环")
        
        while self.is_running:
            loop_start = time.time()
            
            try:
                # 处理新区块
                self.last_block = await self._process_new_blocks(self.last_block)
                
                # 检查确认状态
                await self.confirmation_manager.check_confirmations()
                
                # 定期维护任务
                await self._periodic_maintenance()
                
                # 控制循环频率
                await self._control_loop_timing(loop_start)
                
            except KeyboardInterrupt:
                logger.info("接收到中断信号，准备退出...")
                break
            except Exception as e:
                logger.error(f"监控循环发生错误: {e}", exc_info=True)
                await asyncio.sleep(5)
        
        logger.info("监控循环已停止")
    
    async def _process_new_blocks(self, last_block: int) -> int:
        """处理新区块"""
        try:
            current_block = await self.rpc_manager.get_cached_block_number()
            await self.rpc_manager.check_rate_limit()
        except Exception as e:
            logger.error(f"获取当前区块号失败: {e}")
            return last_block
        
        new_blocks_processed = 0
        
        # 处理新区块
        for block_number in range(last_block + 1, current_block + 1):
            if not self.is_running:
                break
            
            try:
                processed = await self._process_single_block(block_number)
                if processed:
                    new_blocks_processed += 1
                    self.stats_reporter.increment_blocks_processed()
                    
            except BlockNotFound:
                logger.debug(f"区块 {block_number} 未找到，可能还未生成")
                continue
            except Exception as e:
                logger.error(f"处理区块 {block_number} 失败: {e}")
                continue
        
        # 记录处理进度
        if new_blocks_processed > 0:
            self.stats_reporter.log_processing_progress(
                new_blocks_processed, current_block,
                self.rpc_manager, self.tx_processor, self.confirmation_manager
            )
        
        return current_block
    
    async def _process_single_block(self, block_number: int) -> bool:
        """处理单个区块"""
        try:
            block = await self.rpc_manager.get_block(block_number)
            await self.rpc_manager.check_rate_limit()
            
            # 处理区块中的所有交易
            transactions_found = 0
            for tx in block.transactions:
                if not self.is_running:
                    break
                
                tx_info = await self.tx_processor.process_transaction(tx)
                if tx_info:
                    tx = tx_info.tx
                    if tx['from'].lower() == tx['to'].lower():
                        logger.warning(
                            f"⚠️ 代币转账检测到发送地址和接收地址相同: {tx['from']} => {tx['to']} | "
                            f"忽略本次交易"
                        )
                        continue
                    self.confirmation_manager.add_pending_transaction(tx_info)
                    transactions_found += 1
            
            if transactions_found > 0:
                if self.config.is_large_amount_strategy():
                    logger.debug(f"区块 {block_number} 发现 {transactions_found} 笔大额交易")
                else:
                    logger.debug(f"区块 {block_number} 发现 {transactions_found} 笔监控地址交易")
            
            return True
            
        except Exception as e:
            logger.error(f"处理区块 {block_number} 时出错: {e}", exc_info=True)
            return False
    
    async def _periodic_maintenance(self) -> None:
        """定期维护任务"""
        current_time = time.time()
        
        # 每分钟清理一次超时交易
        if current_time % 60 < 1:
            timeout_count = self.confirmation_manager.cleanup_timeout_transactions()
            if timeout_count > 0:
                logger.info(f"🧹 清理了 {timeout_count} 个超时交易")
        
        # 定期输出统计信息
        if self.stats_reporter.should_log_stats():
            self.stats_reporter.log_performance_stats(
                self.rpc_manager, self.tx_processor, self.confirmation_manager
            )
    
    async def _control_loop_timing(self, loop_start: float) -> None:
        """控制循环时间"""
        loop_time = time.time() - loop_start
        
        if loop_time > self.config.block_time:
            logger.warning(f"⚠️ 处理耗时 {loop_time:.2f}s，可能跟不上出块速度 {self.config.block_time}")
            await asyncio.sleep(0.1)
        else:
            # 保持合理的轮询间隔
            await asyncio.sleep(max(0.1, 1 - loop_time))
    
    def stop(self) -> None:
        """停止监控"""
        if not self.is_running:
            logger.info("监控器未在运行")
            return
        
        self.is_running = False
        logger.info("正在停止监控...")
    
    def get_status(self) -> MonitorStatus:
        """获取当前监控状态"""
        return self.stats_reporter.get_monitor_status(self.last_block, self.is_running)
    
    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """获取全面的统计信息"""
        return self.stats_reporter.get_comprehensive_report(
            self.rpc_manager, self.tx_processor, self.confirmation_manager
        )
    
    # 策略管理方法
    def set_monitor_strategy(self, strategy_name: str) -> None:
        """设置监控策略"""
        try:
            strategy = MonitorStrategy(strategy_name)
            old_strategy = self.config.monitor_strategy
            self.config.set_strategy(strategy)
            
            # 同步更新交易处理器的配置
            self.tx_processor.config = self.config
            
            logger.info(f"🔧 监控策略已更新: {old_strategy.value} => {strategy.value}")
            logger.info(f"📋 当前策略: {self.config.get_strategy_description()}")
        except ValueError:
            logger.error(f"无效的监控策略: {strategy_name}")
            logger.info("可用策略: large_amount, watch_address")
    
    # 大额交易策略相关方法
    def update_thresholds(self, **thresholds) -> None:
        """动态更新交易阈值（仅在大额交易策略下有效）"""
        if not self.config.is_large_amount_strategy():
            logger.warning("当前策略为地址监控，阈值设置无效")
            return
        
        old_thresholds = self.config.thresholds.copy()
        
        for token, threshold in thresholds.items():
            if token in self.config.thresholds:
                old_threshold = self.config.thresholds[token]
                self.config.thresholds[token] = threshold
                logger.info(f"🔧 更新{token}阈值: {old_threshold:,.0f} => {threshold:,.0f}")
            else:
                self.config.thresholds[token] = threshold
                logger.info(f"🔧 添加{token}阈值: {threshold:,.0f}")
        
        # 同步更新交易处理器的配置
        self.tx_processor.config = self.config
        
        logger.info(f"📈 当前阈值: {self.config.thresholds}")
    
    # 地址监控策略相关方法
    def add_watch_address(self, address: str) -> None:
        """添加监控地址"""
        self.config.add_watch_address(address)
        self.tx_processor.config = self.config
        logger.info(f"🔧 添加监控地址: {address}")
        logger.info(f"👁️ 当前监控地址数量: {len(self.config.watch_addresses)}")
    
    def remove_watch_address(self, address: str) -> None:
        """移除监控地址"""
        self.config.remove_watch_address(address)
        self.tx_processor.config = self.config
        logger.info(f"🔧 移除监控地址: {address}")
        logger.info(f"👁️ 当前监控地址数量: {len(self.config.watch_addresses)}")
    
    def update_watch_addresses(self, addresses: list) -> None:
        """更新监控地址列表"""
        self.config.watch_addresses = addresses
        self.tx_processor.config = self.config
        logger.info(f"🔧 监控地址列表已更新: {len(addresses)} 个地址")
    
    def update_config(self, **config_updates) -> None:
        """更新配置参数"""
        for key, value in config_updates.items():
            if hasattr(self.config, key):
                old_value = getattr(self.config, key)
                setattr(self.config, key, value)
                logger.info(f"🔧 更新配置 {key}: {old_value} => {value}")
            else:
                logger.warning(f"⚠️ 未知的配置项: {key}")
    
    def reset_all_stats(self) -> None:
        """重置所有统计数据"""
        self.rpc_manager.reset_stats()
        self.tx_processor.reset_stats()
        self.confirmation_manager.reset_stats()
        self.stats_reporter.reset_stats()
        
        # 重置通知服务统计
        if self.notification_service:
            self.notification_service.reset_stats()
        
        logger.info("🔄 所有统计数据已重置")
    
    async def test_notification_webhook(self) -> bool:
        """
        测试通知 Webhook 连接
        
        Returns:
            bool: 测试是否成功
        """
        if not self.notification_initializer:
            logger.warning("通知服务未初始化")
            return False
        
        return await self.notification_initializer.test_webhook_connection_async()
    
    def log_final_report(self) -> None:
        """输出最终报告"""
        self.stats_reporter.log_final_stats(
            self.rpc_manager, self.tx_processor, self.confirmation_manager
        )
    
    async def graceful_shutdown(self) -> None:
        """优雅关闭"""
        logger.info("开始优雅关闭...")
        
        # 停止接收新的区块
        self.stop()
        
        # 关闭通知调度器
        if self.notification_initializer:
            try:
                self.notification_initializer.cleanup()
                logger.info("✅ 通知服务已关闭")
            except Exception as e:
                logger.error(f"❌ 关闭通知服务失败: {e}")
        
        # 关闭 RabbitMQ 消费者
        await self.rabbitmq_initializer.cleanup()
        
        # 关闭数据库连接
        if self.database_initializer:
            try:
                self.database_initializer.cleanup()
                logger.info("✅ 数据库连接已关闭")
            except Exception as e:
                logger.error(f"❌ 关闭数据库连接失败: {e}")
        
        # 等待当前处理完成
        await asyncio.sleep(1)
        
        # 最后一次检查确认状态
        if self.confirmation_manager.has_pending_transactions():
            logger.info("等待最后的确认检查...")
            await self.confirmation_manager.check_confirmations()
        
        # 输出最终报告
        self.log_final_report()
        
        logger.info("监控器已优雅关闭")
    
    async def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        rpc_healthy = self.rpc_manager.is_healthy()
        pending_count = self.confirmation_manager.get_pending_count()
        oldest_pending = self.confirmation_manager.get_oldest_pending_age()
        
        # RabbitMQ 状态
        rabbitmq_status = None
        rabbitmq_healthy = True
        if self.rabbitmq_enabled and self.rabbitmq_consumer:
            try:
                rabbitmq_status = self.rabbitmq_consumer.get_status()
                rabbitmq_healthy = rabbitmq_status.get('connected', False) and rabbitmq_status.get('consuming', False)
            except Exception as e:
                logger.error(f"获取 RabbitMQ 状态失败: {e}")
                rabbitmq_healthy = False
        
        # 数据库状态
        database_healthy = True
        database_stats = None
        if self.database_initializer:
            try:
                database_healthy = self.database_initializer.is_connected()
                database_stats = self.database_initializer.get_stats()
            except Exception as e:
                logger.error(f"获取数据库状态失败: {e}")
                database_healthy = False
        
        # 通知服务状态
        notification_healthy = True
        notification_stats = None
        if self.notification_initializer:
            try:
                notification_healthy = self.notification_initializer.is_healthy()
                notification_stats = self.notification_initializer.get_notification_stats()
            except Exception as e:
                logger.error(f"获取通知服务状态失败: {e}")
                notification_healthy = False
        
        # 判断整体健康状态
        is_healthy = (
            self.is_running and 
            rpc_healthy and 
            pending_count < 100 and  # 待确认交易不超过100笔
            oldest_pending < 3600 and    # 最老的待确认交易不超过1小时
            (not self.rabbitmq_enabled or rabbitmq_healthy) and  # RabbitMQ 必须健康（如果启用）
            database_healthy and  # 数据库必须健康（如果启用）
            notification_healthy  # 通知服务必须健康（如果启用）
        )
        
        health_data = {
            'overall_healthy': is_healthy,
            'is_running': self.is_running,
            'rpc_healthy': rpc_healthy,
            'pending_transactions': pending_count,
            'oldest_pending_age': oldest_pending,
            'blocks_processed': self.stats_reporter.blocks_processed,
            'current_block': self.last_block,
            'uptime_hours': (time.time() - self.stats_reporter.start_time) / 3600,
            'rabbitmq_enabled': self.rabbitmq_enabled,
            'rabbitmq_healthy': rabbitmq_healthy,
            'database_healthy': database_healthy,
            'notification_enabled': self.notification_enabled,
            'notification_healthy': notification_healthy,
            'scheduler_started': self.scheduler_started
        }
        
        if rabbitmq_status:
            health_data['rabbitmq_status'] = rabbitmq_status
        
        if database_stats:
            health_data['database_stats'] = database_stats
            
        if notification_stats:
            health_data['notification_stats'] = notification_stats
            
        return health_data


def setup_signal_handlers(monitor: EVMMonitor) -> None:
    """设置信号处理器"""
    def signal_handler(signum, frame):
        """信号处理器"""
        logger.info(f"接收到信号 {signum}，开始优雅退出...")
        asyncio.create_task(monitor.graceful_shutdown())
    
    # 注册信号处理器
    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        logger.info("信号处理器已注册")
    except Exception as e:
        logger.warning(f"注册信号处理器失败: {e}")


async def main(chain_name: str = 'bsc') -> None:
    """主函数
    
    Args:
        chain_name: 链名称，用于区分不同的监控实例
    """
    # 创建配置
    config = MonitorConfig.from_chain_name(chain_name)
    
    # 创建代币解析器
    token_parser = TokenParser(config)

    # 创建监控器（传入链名称）
    monitor = EVMMonitor(config, token_parser, chain_name=chain_name)
    
    # 设置信号处理器
    setup_signal_handlers(monitor)
    
    try:
        # 开始监控
        await monitor.start_monitoring()
    except KeyboardInterrupt:
        logger.info("接收到键盘中断")
    except Exception as e:
        logger.error(f"监控器运行失败: {e}", exc_info=True)
    finally:
        await monitor.graceful_shutdown()


if __name__ == '__main__':
    import sys
    
    # 支持命令行参数指定链名称
    if len(sys.argv) > 1:
        chain_name = sys.argv[1]
    else:
        chain_name = 'bsc'  # 默认使用 BSC 链
    
    logger.info(f"🚀 启动 {chain_name.upper()} 链监控器")
    asyncio.run(main(chain_name))
