"""
简化测试脚本 - 验证重构后的监控器是否正常工作
"""

import asyncio
import sys
import os

# 将当前目录添加到Python路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.monitor_config import MonitorConfig
from utils.token_parser import TokenParser
from core.evm_monitor import EVMMonitor
from utils.log_utils import get_logger

logger = get_logger(__name__)


async def test_simple():
    """简单测试"""
    try:
        print("=" * 60)
        print("  EVM 监控器重构测试")
        print("=" * 60)
        
        # 1. 测试配置加载
        print("[CONFIG] 测试配置加载...")
        config = MonitorConfig.from_chain_name('bsc')
        print(f"[SUCCESS] 配置加载成功: {config.rpc_url}")
        
        # 2. 测试代币解析器
        print("[TOKEN] 测试代币解析器...")
        token_parser = TokenParser('bsc')  # 传入字符串而不是MonitorConfig对象
        print(f"[SUCCESS] 代币解析器创建成功，支持代币: {list(token_parser.contracts.keys())}")
        
        # 3. 测试监控器创建
        print("[MONITOR] 测试监控器创建...")
        monitor = EVMMonitor(config, token_parser, chain_name='bsc')
        print("[SUCCESS] 监控器创建成功")
        
        # 4. 测试组件初始化状态
        print("[COMPONENTS] 检查组件状态...")
        print(f"   - 数据库初始化器: {'存在' if monitor.database_initializer else '不存在'}")
        print(f"   - 通知初始化器: {'存在' if monitor.notification_initializer else '不存在'}")
        print(f"   - 通知服务: {'启用' if monitor.notification_enabled else '禁用'}")
        print(f"   - 调度器: {'已启动' if monitor.scheduler_started else '未启动'}")
        
        # 5. 测试健康检查
        print("[HEALTH] 测试健康检查...")
        health_status = await monitor.get_health_status()
        print("[SUCCESS] 健康检查完成:")
        print(f"   - RPC健康: {'是' if health_status['rpc_healthy'] else '否'}")
        print(f"   - 数据库健康: {'是' if health_status['database_healthy'] else '否'}")
        print(f"   - 通知服务: {'是' if health_status['notification_healthy'] else '否'}")
        print(f"   - RabbitMQ: {'是' if health_status['rabbitmq_healthy'] else '否'}")
        
        # 6. 测试优雅关闭
        print("[SHUTDOWN] 测试优雅关闭...")
        await monitor.graceful_shutdown()
        print("[SUCCESS] 优雅关闭测试完成")
        
        print("\n[RESULT] 所有测试通过！监控器重构成功！")
        return True
        
    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_service_components():
    """测试各个服务组件"""
    try:
        print("[SERVICES] 测试各个服务组件...")
        
        # 测试数据库初始化器
        from core.database_initializer import DatabaseInitializer
        from config.base_config import DatabaseConfig
        
        db_initializer = DatabaseInitializer(DatabaseConfig)
        print("[SUCCESS] 数据库初始化器创建成功")
        
        # 测试通知初始化器
        from core.notification_initializer import NotificationInitializer
        from config.base_config import NotifyConfig
        
        notification_initializer = NotificationInitializer(NotifyConfig)
        print("[SUCCESS] 通知初始化器创建成功")
        
        # 测试通知服务
        from services.notification_service import NotificationService
        
        notification_service = NotificationService("http://test.example.com/webhook")
        print("[SUCCESS] 通知服务创建成功")
        
        print("[RESULT] 所有服务组件测试通过！")
        return True
        
    except Exception as e:
        print(f"[ERROR] 服务组件测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    success = True
    
    # 测试服务组件
    if not await test_service_components():
        success = False
    
    print()  # 空行分隔
    
    # 测试监控器初始化
    if not await test_simple():
        success = False
    
    if success:
        print("\n[FINAL] 所有测试通过！系统重构成功！")
        return 0
    else:
        print("\n[FINAL] 部分测试失败，请检查错误信息")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
