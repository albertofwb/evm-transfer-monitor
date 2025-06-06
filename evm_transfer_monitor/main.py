#!/usr/bin/env python3
"""
EVM转账监控器 - 重构版本

程序入口点，启动监控器
"""

import asyncio
import sys
import os

# 将当前目录添加到Python路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.evm_monitor import EVMMonitor, setup_signal_handlers
from config.monitor_config import MonitorConfig
from utils.log_utils import get_logger

logger = get_logger(__name__)


async def main():
    """主函数 - 启动EVM监控器"""
    try:
        # 创建配置
        config = MonitorConfig()
        
        # 创建监控器
        monitor = EVMMonitor(config)
        
        # 设置信号处理器
        setup_signal_handlers(monitor)
        
        # 开始监控
        await monitor.start_monitoring()
        
    except KeyboardInterrupt:
        logger.info("接收到键盘中断")
    except Exception as e:
        logger.error(f"监控器运行失败: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
