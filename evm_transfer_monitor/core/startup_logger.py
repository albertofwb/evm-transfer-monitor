"""
启动信息记录模块

负责记录监控器启动时的详细信息和配置状态
"""

from config.monitor_config import MonitorConfig
from utils.log_utils import get_logger

logger = get_logger(__name__)


class StartupLogger:
    """启动信息记录器"""
    
    def __init__(self, config: MonitorConfig):
        """
        初始化启动信息记录器
        
        Args:
            config: 监控配置
        """
        self.config = config
    
    def log_startup_info(self) -> None:
        """记录启动信息"""
        logger.info("🚀 开始监控 EVM 链交易")
        
        # 显示基本配置信息
        self._log_basic_config()
        
        # 显示当前策略详情
        self._log_strategy_details()
        
        # 显示确认配置
        self._log_confirmation_config()
    
    def _log_basic_config(self) -> None:
        """记录基本配置信息"""
        logger.info(f"🔗 RPC URL: {self.config.rpc_url}")
        logger.info(f"⏱️ 区块时间: {self.config.block_time} 秒")
    
    def _log_strategy_details(self) -> None:
        """记录策略详细信息"""
        strategy_desc = self.config.get_strategy_description()
        logger.info(f"📋 监控策略: {strategy_desc}")
        
        if self.config.is_large_amount_strategy():
            self._log_large_amount_strategy()
        elif self.config.is_watch_address_strategy():
            self._log_watch_address_strategy()
    
    def _log_large_amount_strategy(self) -> None:
        """记录大额交易策略信息"""
        thresholds = self.config.thresholds
        threshold_info = " | ".join([
            f"{token}≥{amount:,.0f}" for token, amount in thresholds.items()
        ])
        logger.info(f"📈 监控阈值: {threshold_info}")
    
    def _log_watch_address_strategy(self) -> None:
        """记录地址监控策略信息"""
        addresses_count = len(self.config.watch_addresses)
        logger.info(f"👁️ 监控地址数量: {addresses_count}")
        
        # 显示前5个地址作为示例
        for i, addr in enumerate(self.config.watch_addresses[:5], 1):
            logger.info(f"   {i}. {addr}")
        
        # 如果地址数量超过5个，显示省略信息
        if addresses_count > 5:
            logger.info(f"   ... 还有 {addresses_count - 5} 个地址")
    
    def _log_confirmation_config(self) -> None:
        """记录确认配置信息"""
        logger.info(f"⚙️ 确认要求: {self.config.required_confirmations} 个区块")
