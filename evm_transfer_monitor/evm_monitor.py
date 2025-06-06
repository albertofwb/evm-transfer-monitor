"""
主监控器类

协调各个组件，提供统一的监控接口和控制逻辑
"""

import asyncio
import signal
import time
from typing import Optional, Dict, Any

from web3.exceptions import BlockNotFound

from monitor_config import MonitorConfig
from rpc_manager import RPCManager
from transaction_processor import TransactionProcessor
from confirmation_manager import ConfirmationManager
from statistics_reporter import StatisticsReporter
from data_types import MonitorStatus
from token_parser import TokenParser
from log_utils import get_logger

logger = get_logger(__name__)


class EVMMonitor:
    """主监控器类 - 协调各个组件"""
    
    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()
        self.is_running = False
        self.last_block = 0
        
        # 初始化各个组件
        self.rpc_manager = RPCManager(self.config)
        self.tx_processor = TransactionProcessor(self.config, self.rpc_manager)
        self.confirmation_manager = ConfirmationManager(self.config, self.rpc_manager)
        self.stats_reporter = StatisticsReporter(self.config)
    
    async def start_monitoring(self) -> None:
        """开始监控"""
        if self.is_running:
            logger.warning("监控器已在运行中")
            return
        
        self.is_running = True
        
        try:
            # 检查网络连接
            await self._check_network_connection()
            
            # 显示启动信息
            self._log_startup_info()
            
            # 获取起始区块
            self.last_block = await self.rpc_manager.get_cached_block_number()
            
            # 主监控循环
            await self._monitoring_loop()
            
        except Exception as e:
            logger.error(f"监控启动失败: {e}", exc_info=True)
            self.is_running = False
            raise
    
    async def _check_network_connection(self) -> None:
        """检查网络连接"""
        connection_info = await self.rpc_manager.test_connection()
        
        if connection_info['success']:
            logger.info(
                f"🌐 {connection_info['network']} 连接成功 - "
                f"区块: {connection_info['latest_block']}, "
                f"Gas: {connection_info['gas_price_gwei']:.2f} Gwei"
            )
            
            # 显示支持的代币信息
            self._log_supported_tokens()
        else:
            logger.error(f"网络连接失败: {connection_info['error']}")
            raise ConnectionError(f"无法连接到RPC: {connection_info['error']}")
    
    def _log_supported_tokens(self) -> None:
        """记录支持的代币信息"""
        logger.info("🪙 支持的代币合约:")
        for token, contract in TokenParser.CONTRACTS.items():
            if contract:
                logger.info(f"   {token}: {contract}")
    
    def _log_startup_info(self) -> None:
        """记录启动信息"""
        logger.info("🚀 开始监控 EVM 链交易（包含代币转账）")
        thresholds = self.config.thresholds
        threshold_info = " | ".join([
            f"{token}≥{amount:,.0f}" for token, amount in thresholds.items()
        ])
        logger.info(f"📈 监控阈值: {threshold_info}")
        logger.info(f"⚙️ 确认要求: {self.config.required_confirmations} 个区块")
    
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
                    self.confirmation_manager.add_pending_transaction(tx_info)
                    transactions_found += 1
            
            if transactions_found > 0:
                logger.debug(f"区块 {block_number} 发现 {transactions_found} 笔大额交易")
            
            return True
            
        except Exception as e:
            logger.error(f"处理区块 {block_number} 时出错: {e}")
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
        
        if loop_time > 2:
            logger.warning(f"⚠️ 处理耗时 {loop_time:.2f}s，可能跟不上出块速度")
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
    
    def update_thresholds(self, **thresholds) -> None:
        """动态更新交易阈值"""
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
        logger.info("🔄 所有统计数据已重置")
    
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
        
        # 等待当前处理完成
        await asyncio.sleep(1)
        
        # 最后一次检查确认状态
        if self.confirmation_manager.has_pending_transactions():
            logger.info("等待最后的确认检查...")
            await self.confirmation_manager.check_confirmations()
        
        # 输出最终报告
        self.log_final_report()
        
        logger.info("监控器已优雅关闭")
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        rpc_healthy = self.rpc_manager.is_healthy()
        pending_count = self.confirmation_manager.get_pending_count()
        oldest_pending = self.confirmation_manager.get_oldest_pending_age()
        
        # 判断整体健康状态
        is_healthy = (
            self.is_running and 
            rpc_healthy and 
            pending_count < 100 and  # 待确认交易不超过100笔
            oldest_pending < 3600    # 最老的待确认交易不超过1小时
        )
        
        return {
            'overall_healthy': is_healthy,
            'is_running': self.is_running,
            'rpc_healthy': rpc_healthy,
            'pending_transactions': pending_count,
            'oldest_pending_age': oldest_pending,
            'blocks_processed': self.stats_reporter.blocks_processed,
            'current_block': self.last_block,
            'uptime_hours': (time.time() - self.stats_reporter.start_time) / 3600
        }


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


async def main():
    """主函数"""
    # 创建配置
    config = MonitorConfig()
    
    # 创建监控器
    monitor = EVMMonitor(config)
    
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
    asyncio.run(main())
