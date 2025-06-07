#!/usr/bin/env python3
"""
测试启动脚本
"""

import sys
import os

# 将当前目录添加到Python路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("1. 测试基础导入...")
    from config.monitor_config import MonitorConfig
    from utils.token_parser import TokenParser
    from utils.log_utils import get_logger
    print("[OK] 基础模块导入成功")

    print("\n2. 测试配置创建...")
    config = MonitorConfig.from_chain_name('bsc')
    token_parser = TokenParser('bsc')
    print("[OK] 配置创建成功")

    print("\n3. 测试EVMMonitor导入...")
    from core.evm_monitor import EVMMonitor, setup_signal_handlers
    print("[OK] EVMMonitor导入成功")

    print("\n4. 测试EVMMonitor实例化...")
    monitor = EVMMonitor(config, token_parser, chain_name='bsc')
    print("[OK] EVMMonitor实例化成功")

    print("\n5. 检查监控器状态...")
    print(f"链名称: {monitor.chain_name}")
    print(f"RPC URL: {monitor.config.rpc_url}")
    print(f"监控策略: {monitor.config.get_strategy_description()}")
    print(f"RabbitMQ 启用: {monitor.rabbitmq_enabled}")
    
    print("\n[OK] 所有测试通过！程序可以正常启动。")

except Exception as e:
    print(f"[ERROR] 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
