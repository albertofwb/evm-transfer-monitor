"""
使用示例

演示如何使用通知系统的各个组件
"""

import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# 导入我们创建的模块
from models.notification_models import Base, DepositRecord, NotificationRecord
from models.transaction_adapter import TransactionAdapter
from models.data_types import TransactionInfo
from services.notification_service import NotificationService, NotificationConfig
from scheduler.notification_scheduler import NotificationScheduler, NotificationSchedulerContext

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def setup_database():
    """设置数据库连接"""
    # 示例：使用 SQLite 数据库
    engine = create_engine('sqlite:///deposit_monitor.db', echo=False)
    
    # 创建表
    Base.metadata.create_all(engine)
    
    # 创建会话
    Session = sessionmaker(bind=engine)
    return Session()


def example_save_transaction():
    """示例：保存交易信息"""
    logger.info("=== 保存交易信息示例 ===")
    
    # 设置数据库
    db_session = setup_database()
    adapter = TransactionAdapter(db_session)
    
    # 模拟一个 TransactionInfo 对象
    transaction_info = TransactionInfo(
        hash="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        tx={
            "blockHash": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "from": "0xfrom1234567890123456789012345678901234567890",
            "to": "0xto1234567890123456789012345678901234567890",
            "gasUsed": "21000",
            "gasPrice": "20000000000"  # 20 Gwei
        },
        value=1.5,  # 1.5 ETH
        tx_type="transfer",
        found_at=datetime.now().timestamp(),
        block_number=18000000
    )
    
    # 保存交易
    deposit_record = adapter.save_transaction_info(transaction_info, user_id="user123")
    
    if deposit_record:
        logger.info(f"交易保存成功: {deposit_record.tx_hash}")
        
        # 模拟交易确认
        adapter.update_transaction_status(deposit_record.tx_hash, "confirmed", 12)
        logger.info("交易状态已更新为已确认")
    
    db_session.close()


def example_notification_service():
    """示例：通知服务使用"""
    logger.info("=== 通知服务示例 ===")
    
    # 设置数据库和配置
    db_session = setup_database()
    
    config = NotificationConfig()
    config.enabled = True
    config.webhook_url = "https://your-webhook-url.com/notifications"
    config.max_attempts = 3
    config.retry_delay = 10
    
    # 创建通知服务
    notification_service = NotificationService(db_session, config)
    
    # 查找需要通知的充值记录
    confirmed_records = db_session.query(DepositRecord).filter(
        DepositRecord.status == 'confirmed',
        DepositRecord.confirmations >= 12,
        DepositRecord.notification_generated == False
    ).all()
    
    logger.info(f"找到 {len(confirmed_records)} 条需要通知的记录")
    
    # 为每条记录创建并发送通知
    for record in confirmed_records:
        notification = notification_service.create_notification_record(record)
        if notification:
            success = notification_service.send_notification(notification)
            logger.info(f"通知发送{'成功' if success else '失败'}: {record.tx_hash}")
    
    # 获取通知统计
    stats = notification_service.get_notification_stats()
    logger.info(f"通知统计: {stats}")
    
    db_session.close()


def example_scheduler():
    """示例：调度器使用"""
    logger.info("=== 调度器示例 ===")
    
    # 设置数据库和配置
    db_session = setup_database()
    
    config = NotificationConfig()
    config.enabled = True
    config.webhook_url = "https://your-webhook-url.com/notifications"
    config.retry_delay = 5  # 5秒重试间隔
    config.cleanup_days = 7  # 保留7天记录
    
    notification_service = NotificationService(db_session, config)
    
    # 使用上下文管理器自动管理调度器生命周期
    try:
        with NotificationSchedulerContext(db_session, notification_service, config) as scheduler:
            logger.info("调度器已启动")
            
            # 处理待通知的记录
            processed = scheduler.process_pending_notifications(required_confirmations=12)
            logger.info(f"处理了 {processed} 条待通知记录")
            
            # 获取调度器状态
            status = scheduler.get_status()
            logger.info(f"调度器状态: {status}")
            
            # 模拟运行一段时间
            import time
            logger.info("调度器运行中...")
            time.sleep(30)  # 运行30秒
            
    except KeyboardInterrupt:
        logger.info("收到中断信号，停止调度器")
    
    db_session.close()


def example_token_transaction():
    """示例：代币交易处理"""
    logger.info("=== 代币交易示例 ===")
    
    db_session = setup_database()
    adapter = TransactionAdapter(db_session)
    
    # 模拟一个代币交易
    token_transaction = TransactionInfo(
        hash="0xtoken123456789abcdef123456789abcdef123456789abcdef123456789abcdef",
        tx={
            "blockHash": "0xblock123456789abcdef123456789abcdef123456789abcdef123456789abc",
            "from": "0xfrom1234567890123456789012345678901234567890",
            "to": "0xcontract1234567890123456789012345678901234567890",  # 合约地址
            "gasUsed": "65000",
            "gasPrice": "25000000000"  # 25 Gwei
        },
        value=1000.0,  # 1000 代币
        tx_type="token_transfer",
        found_at=datetime.now().timestamp(),
        block_number=18000001,
        token_info={
            "contract_address": "0xcontract1234567890123456789012345678901234567890",
            "symbol": "USDT",
            "decimals": 6,
            "from": "0xfrom1234567890123456789012345678901234567890",
            "to": "0xto1234567890123456789012345678901234567890"
        }
    )
    
    # 保存代币交易
    deposit_record = adapter.save_transaction_info(token_transaction, user_id="user456")
    
    if deposit_record:
        logger.info(f"代币交易保存成功: {deposit_record.tx_hash}")
        logger.info(f"代币: {deposit_record.token_symbol}, 数量: {deposit_record.amount}")
    
    db_session.close()


def main():
    """主函数 - 运行所有示例"""
    logger.info("开始运行通知系统示例...")
    
    try:
        # 1. 保存普通交易
        example_save_transaction()
        
        # 2. 保存代币交易
        example_token_transaction()
        
        # 3. 通知服务示例
        example_notification_service()
        
        # 4. 调度器示例（注释掉以避免长时间运行）
        # example_scheduler()
        
        logger.info("所有示例运行完成")
        
    except Exception as e:
        logger.error(f"运行示例时出错: {e}")


if __name__ == "__main__":
    main()
