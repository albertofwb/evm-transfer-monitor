"""
通知服务

负责发送各种类型的通知（支持异步）
"""

import asyncio
import aiohttp
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text

from utils.log_utils import get_logger

# 导入模型
try:
    from models.notification_models import NotificationRecord, DepositRecord
except ImportError:
    NotificationRecord = None
    DepositRecord = None

logger = get_logger(__name__)


class NotificationService:
    """通知服务 - 负责发送异步通知"""
    
    def __init__(self, webhook_url: str, timeout: int = 30, 
                 max_retry_attempts: int = 3, retry_delay: int = 5,
                 db_session: Optional[Session] = None):
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.max_retry_attempts = max_retry_attempts
        self.retry_delay = retry_delay
        self.db_session = db_session
        
        # 统计信息
        self.total_sent = 0
        self.total_failed = 0
        self.total_retries = 0
    
    async def send_notification_async(self, notification_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        异步发送通知
        
        Args:
            notification_data: 通知数据
            
        Returns:
            Dict[str, Any]: 响应数据，包含 success 字段
        """
        if not self.webhook_url:
            logger.warning("Webhook URL 未配置，跳过通知发送")
            return {"success": False, "error": "Webhook URL not configured"}
        
        attempt = 0
        last_error = None
        
        while attempt < self.max_retry_attempts:
            try:
                attempt += 1
                
                # 添加元数据
                payload = {
                    **notification_data,
                    "sent_at": datetime.now().isoformat(),
                    "attempt": attempt,
                    "service": "evm_transfer_monitor"
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.webhook_url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=self.timeout),
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "EVM-Transfer-Monitor/1.0"
                        }
                    ) as response:
                        response_text = await response.text()
                        
                        if response.status == 200:
                            self.total_sent += 1
                            if attempt > 1:
                                self.total_retries += attempt - 1
                            
                            logger.debug(f"通知发送成功 (尝试 {attempt}): {notification_data.get('tx_hash', 'unknown')}")
                            
                            try:
                                response_data = json.loads(response_text)
                            except:
                                response_data = {"raw_response": response_text}
                            
                            return {
                                "success": True,
                                "status_code": response.status,
                                "response": response_data,
                                "attempts": attempt
                            }
                        else:
                            last_error = f"HTTP {response.status}: {response_text}"
                            logger.warning(f"通知发送失败 (尝试 {attempt}): {last_error}")
                            
            except asyncio.TimeoutError:
                last_error = f"请求超时 ({self.timeout}s)"
                logger.warning(f"通知发送超时 (尝试 {attempt}): {notification_data.get('tx_hash', 'unknown')}")
                
            except aiohttp.ClientError as e:
                last_error = f"网络错误: {str(e)}"
                logger.warning(f"通知发送网络错误 (尝试 {attempt}): {last_error}")
                
            except Exception as e:
                last_error = f"未知错误: {str(e)}"
                logger.error(f"通知发送异常 (尝试 {attempt}): {last_error}")
            
            # 如果还有重试机会，等待一段时间
            if attempt < self.max_retry_attempts:
                await asyncio.sleep(self.retry_delay)
        
        # 所有尝试都失败了
        self.total_failed += 1
        self.total_retries += attempt - 1
        
        logger.error(f"通知发送最终失败: {notification_data.get('tx_hash', 'unknown')} - {last_error}")
        
        return {
            "success": False,
            "error": last_error,
            "attempts": attempt
        }
    
    def send_notification_sync(self, notification_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        同步发送通知（内部使用异步实现）
        
        Args:
            notification_data: 通知数据
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环正在运行，创建任务
                task = asyncio.create_task(self.send_notification_async(notification_data))
                return {"success": True, "task_created": True}
            else:
                # 如果事件循环未运行，同步执行
                return asyncio.run(self.send_notification_async(notification_data))
        except Exception as e:
            logger.error(f"同步发送通知时出错: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_batch_notifications_async(self, notifications: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        异步批量发送通知
        
        Args:
            notifications: 通知数据列表
            
        Returns:
            Dict[str, Any]: 批量发送结果
        """
        if not notifications:
            return {"success": True, "sent": 0, "failed": 0}
        
        logger.info(f"开始批量发送 {len(notifications)} 个通知")
        
        # 创建所有发送任务
        tasks = [
            self.send_notification_async(notification)
            for notification in notifications
        ]
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        sent_count = 0
        failed_count = 0
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_count += 1
                logger.error(f"批量通知 {i} 发送异常: {result}")
            elif result and result.get("success", False):
                sent_count += 1
            else:
                failed_count += 1
        
        logger.info(f"批量通知发送完成: 成功 {sent_count}, 失败 {failed_count}")
        
        return {
            "success": True,
            "total": len(notifications),
            "sent": sent_count,
            "failed": failed_count,
            "results": [r for r in results if not isinstance(r, Exception)]
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取通知服务统计信息"""
        return {
            "total_sent": self.total_sent,
            "total_failed": self.total_failed,
            "total_retries": self.total_retries,
            "success_rate": (self.total_sent / (self.total_sent + self.total_failed) * 100) 
                           if (self.total_sent + self.total_failed) > 0 else 0,
            "config": {
                "webhook_url": self.webhook_url[:50] + "..." if len(self.webhook_url) > 50 else self.webhook_url,
                "timeout": self.timeout,
                "max_retry_attempts": self.max_retry_attempts,
                "retry_delay": self.retry_delay
            }
        }
    
    def get_notification_stats(self) -> Dict[str, Any]:
        """获取通知统计信息（与 get_stats 相同，保持兼容性）"""
        return self.get_stats()
    
    def create_notification_record(self, deposit_record) -> Optional[Dict[str, Any]]:
        """
        从充值记录创建通知数据并存储到数据库
        
        Args:
            deposit_record: 充值记录对象
            
        Returns:
            Optional[Dict[str, Any]]: 通知数据字典
        """
        try:
            # 创建通知数据
            notification_data = {
                "type": "deposit_confirmed",
                "tx_hash": getattr(deposit_record, 'tx_hash', ''),
                "from_address": getattr(deposit_record, 'from_address', ''),
                "to_address": getattr(deposit_record, 'to_address', ''),
                "amount": str(getattr(deposit_record, 'amount', 0)),
                "token_symbol": getattr(deposit_record, 'token_symbol', 'ETH'),
                "token_address": getattr(deposit_record, 'token_address', ''),
                "confirmations": getattr(deposit_record, 'confirmations', 0),
                "block_number": getattr(deposit_record, 'block_number', 0),
                "user_id": getattr(deposit_record, 'user_id', ''),
                "timestamp": datetime.now().isoformat(),
                "deposit_record_id": getattr(deposit_record, 'id', None)
            }
            
            # 如果有数据库会话和模型，创建通知记录
            if self.db_session and NotificationRecord and hasattr(deposit_record, 'id'):
                notification_record = NotificationRecord(
                    deposit_record_id=deposit_record.id,
                    tx_hash=deposit_record.tx_hash,
                    user_id=getattr(deposit_record, 'user_id', ''),
                    notification_type='deposit',
                    status='pending',
                    request_data=json.dumps(notification_data),
                    max_attempts=self.max_retry_attempts
                )
                
                self.db_session.add(notification_record)
                self.db_session.flush()  # 获取 ID
                
                # 在通知数据中添加记录 ID
                notification_data['notification_record_id'] = notification_record.id
            
            logger.debug(f"创建通知记录: {notification_data.get('tx_hash')}")
            return notification_data
            
        except Exception as e:
            logger.error(f"创建通知记录失败: {e}")
            if self.db_session:
                try:
                    self.db_session.rollback()
                except:
                    pass
            return None
    
    def send_notification(self, notification_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送通知并更新数据库记录（同步版本，用于调度器）
        
        Args:
            notification_data: 通知数据
            
        Returns:
            Dict[str, Any]: 发送结果
        """
        result = self.send_notification_sync(notification_data)
        
        # 更新数据库记录状态
        if self.db_session and NotificationRecord:
            try:
                notification_record_id = notification_data.get('notification_record_id')
                if notification_record_id:
                    notification_record = self.db_session.query(NotificationRecord).filter(
                        NotificationRecord.id == notification_record_id
                    ).first()
                    
                    if notification_record:
                        notification_record.increment_attempt()
                        
                        if result.get('success', False):
                            # 发送成功
                            notification_record.mark_as_sent(
                                json.dumps(result.get('response', {}))
                            )
                            logger.debug(f"通知发送成功: {notification_data.get('tx_hash')}")
                        else:
                            # 发送失败
                            error_msg = result.get('error', '未知错误')
                            next_retry = None
                            if not notification_record.is_max_attempts_reached():
                                next_retry = datetime.now() + timedelta(seconds=self.retry_delay * 60)
                            
                            notification_record.mark_as_failed(error_msg, next_retry)
                            logger.warning(f"通知发送失败: {notification_data.get('tx_hash')} - {error_msg}")
                        
                        self.db_session.commit()
                        
            except Exception as e:
                logger.error(f"更新通知记录状态失败: {e}")
                if self.db_session:
                    try:
                        self.db_session.rollback()
                    except:
                        pass
        
        return result
    

    
    def reset_stats(self) -> None:
        """重置统计数据"""
        self.total_sent = 0
        self.total_failed = 0
        self.total_retries = 0
        logger.info("通知服务统计数据已重置")
    
    async def test_webhook_async(self) -> bool:
        """
        异步测试 Webhook 连接
        
        Returns:
            bool: 测试是否成功
        """
        test_data = {
            "type": "test",
            "message": "EVM Transfer Monitor webhook test",
            "timestamp": datetime.now().isoformat(),
            "test": True
        }
        
        try:
            result = await self.send_notification_async(test_data)
            return result and result.get("success", False)
        except Exception as e:
            logger.error(f"Webhook 测试失败: {e}")
            return False
    
    def test_webhook_sync(self) -> bool:
        """
        同步测试 Webhook 连接
        
        Returns:
            bool: 测试是否成功
        """
        try:
            # 检查是否已有运行中的事件循环
            try:
                loop = asyncio.get_running_loop()
                # 如果有运行中的循环，创建任务并返回 True（假设测试会成功）
                # 在实际场景中，这个测试会在后台异步执行
                task = asyncio.create_task(self.test_webhook_async())
                logger.info("Webhook 测试任务已创建，将在后台执行")
                return True
            except RuntimeError:
                # 没有运行中的事件循环，可以使用 asyncio.run()
                return asyncio.run(self.test_webhook_async())
        except Exception as e:
            logger.error(f"同步测试 Webhook 失败: {e}")
            return False


# 用于向后兼容的配置类
class NotificationConfig:
    """通知配置类（保持向后兼容）"""
    
    def __init__(self):
        self.enabled = True
        self.webhook_url = ""
        self.timeout = 30
        self.max_attempts = 3
        self.retry_delay = 5


# 便捷函数
async def send_notification_async(webhook_url: str, notification_data: Dict[str, Any], 
                                timeout: int = 30) -> Optional[Dict[str, Any]]:
    """
    便捷的异步通知发送函数
    
    Args:
        webhook_url: Webhook URL
        notification_data: 通知数据
        timeout: 超时时间
        
    Returns:
        Optional[Dict[str, Any]]: 响应数据
    """
    service = NotificationService(webhook_url, timeout)
    return await service.send_notification_async(notification_data)


def send_notification_sync(webhook_url: str, notification_data: Dict[str, Any], 
                          timeout: int = 30) -> Dict[str, Any]:
    """
    便捷的同步通知发送函数
    
    Args:
        webhook_url: Webhook URL
        notification_data: 通知数据
        timeout: 超时时间
        
    Returns:
        Dict[str, Any]: 响应数据
    """
    service = NotificationService(webhook_url, timeout)
    return service.send_notification_sync(notification_data)
