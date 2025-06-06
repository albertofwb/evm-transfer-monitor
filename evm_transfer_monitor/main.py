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
from utils.token_parser import TokenParser
logger = get_logger(__name__)


async def main(chain_name: str) -> int:
    """主函数 - 启动EVM监控器"""
    try:
        # 创建配置
        config = MonitorConfig.from_chain_name(chain_name)
        token_parser = TokenParser(chain_name)
        # 创建监控器
        monitor = EVMMonitor(config, token_parser)

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
    chain_name = sys.argv[1] if len(sys.argv) > 1 else "bsc"
    exit_code = asyncio.run(main(chain_name))
    sys.exit(exit_code)
