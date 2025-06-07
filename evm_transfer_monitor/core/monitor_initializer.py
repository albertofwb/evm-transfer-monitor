"""
监控器初始化模块

负责监控器的组件初始化，包括各种管理器的创建和配置
"""

from typing import Optional, Dict, Any

from config.monitor_config import MonitorConfig
from config.base_config import get_rabbitmq_config, DatabaseConfig, NotifyConfig
from managers.rpc_manager import RPCManager
from processors.transaction_processor import TransactionProcessor
from managers.confirmation_manager import ConfirmationManager
from reports.statistics_reporter import StatisticsReporter
from utils.token_parser import TokenParser
from utils.log_utils import get_logger

# 导入新的初始化器
from core.database_initializer import DatabaseInitializer
from core.notification_initializer import NotificationInitializer

logger = get_logger(__name__)


class MonitorInitializer:
    """监控器初始化器 - 负责创建和配置各个组件"""
    
    def __init__(self, config: MonitorConfig, token_parser: TokenParser, chain_name: str):
        """
        初始化器构造函数
        
        Args:
            config: 监控配置
            token_parser: 代币解析器
            chain_name: 链名称
        """
        self.config = config
        self.token_parser = token_parser
        self.chain_name = chain_name
        
        # 初始化数据库和通知服务初始化器
        self.database_initializer = DatabaseInitializer(DatabaseConfig)
        self.notification_initializer = None  # 将在数据库初始化后创建
        
    def init_core_components(self) -> Dict[str, Any]:
        """
        初始化核心组件
        
        Returns:
            包含所有核心组件的字典
        """
        logger.info("🔧 初始化核心组件...")
        
        # 创建RPC管理器
        rpc_manager = RPCManager(self.config)
        logger.debug("✅ RPC管理器已创建")
        
        # 创建交易处理器
        tx_processor = TransactionProcessor(self.config, self.token_parser, rpc_manager)
        logger.debug("✅ 交易处理器已创建")
        
        # 创建确认管理器
        confirmation_manager = ConfirmationManager(self.config, rpc_manager, self.token_parser)
        logger.debug("✅ 确认管理器已创建")
        
        # 创建统计报告器
        stats_reporter = StatisticsReporter(self.config)
        logger.debug("✅ 统计报告器已创建")
        
        return {
            'rpc_manager': rpc_manager,
            'tx_processor': tx_processor,
            'confirmation_manager': confirmation_manager,
            'stats_reporter': stats_reporter
        }
    
    def init_rabbitmq_config(self, custom_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        初始化RabbitMQ配置
        
        Args:
            custom_config: 自定义配置
            
        Returns:
            最终的RabbitMQ配置
        """
        if custom_config:
            logger.debug("使用自定义RabbitMQ配置")
            return custom_config.copy()
        else:
            logger.debug("使用默认RabbitMQ配置")
            return get_rabbitmq_config()
    
    def customize_rabbitmq_config(self, rabbitmq_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        为当前实例定制RabbitMQ配置
        
        Args:
            rabbitmq_config: 原始配置
            
        Returns:
            定制后的配置
        """
        config = rabbitmq_config.copy()
        wallet_config = config.get('wallet_updates', {})
        
        # 为每个链创建独特的交换机名称
        base_exchange = wallet_config.get('exchange_name', 'wallet_updates')
        wallet_config['exchange_name'] = f"{base_exchange}_{self.chain_name}"
        
        # 如果指定了队列名称，也要加上链名称
        if wallet_config.get('queue_name'):
            base_queue = wallet_config['queue_name']
            wallet_config['queue_name'] = f"{base_queue}_{self.chain_name}"
        
        logger.info(f"🔗 {self.chain_name} 链 RabbitMQ 配置:")
        logger.info(f"   交换机: {wallet_config['exchange_name']}")
        if wallet_config.get('queue_name'):
            logger.info(f"   队列: {wallet_config['queue_name']}")
        else:
            logger.info(f"   队列: 自动生成")
            
        return config
    
    def init_database_and_notification(self) -> Dict[str, Any]:
        """
        初始化数据库和通知服务
        
        Returns:
            包含数据库和通知组件的字典
        """
        logger.info("💾 初始化数据库和通知服务...")
        
        # 初始化数据库
        db_success = self.database_initializer.init_database()
        db_session = None
        
        if db_success:
            db_session = self.database_initializer.get_session()
            logger.debug("✅ 数据库初始化成功")
        else:
            logger.warning("⚠️ 数据库初始化失败，将在无数据库模式下运行")
        
        # 初始化通知服务
        self.notification_initializer = NotificationInitializer(NotifyConfig, db_session)
        notification_components = self.notification_initializer.init_notification_service()
        
        # 启动通知调度器（如果数据库可用且通知服务启用）
        scheduler_started = False
        if db_session and notification_components.get('enabled', False):
            scheduler_started = self.notification_initializer.start_scheduler()
        
        return {
            'database_success': db_success,
            'database_initializer': self.database_initializer,
            'db_session': db_session,
            'notification_initializer': self.notification_initializer,
            'notification_service': notification_components.get('service'),
            'notification_scheduler': notification_components.get('scheduler'),
            'notification_enabled': notification_components.get('enabled', False),
            'scheduler_started': scheduler_started
        }
