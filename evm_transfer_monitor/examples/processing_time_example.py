"""
区块处理时间统计示例

展示如何在调用 log_processing_progress 时添加处理时间测量
"""

import time
from typing import Optional

from reports.statistics_reporter import StatisticsReporter
from config.monitor_config import MonitorConfig


class BlockProcessor:
    """区块处理器示例"""
    
    def __init__(self, config: MonitorConfig, stats_reporter: StatisticsReporter):
        self.config = config
        self.stats_reporter = stats_reporter
    
    def process_blocks_batch(self, start_block: int, end_block: int, 
                           rpc_manager, tx_processor, confirmation_manager) -> None:
        """
        处理一批区块并记录处理时间
        
        Args:
            start_block: 起始区块号
            end_block: 结束区块号
            rpc_manager: RPC管理器
            tx_processor: 交易处理器
            confirmation_manager: 确认管理器
        """
        new_blocks = end_block - start_block + 1
        
        # 记录开始时间
        start_time = time.time()
        
        try:
            # 模拟区块处理逻辑
            self._simulate_block_processing(start_block, end_block)
            
            # 更新处理的区块数
            for _ in range(new_blocks):
                self.stats_reporter.increment_blocks_processed()
            
        finally:
            # 计算处理时间
            processing_time = time.time() - start_time
            
            # 记录处理进度，包含处理时间
            self.stats_reporter.log_processing_progress(
                new_blocks=new_blocks,
                current_block=end_block,
                rpc_manager=rpc_manager,
                tx_processor=tx_processor,
                confirmation_manager=confirmation_manager,
                processing_time=processing_time  # 关键：传入处理时间
            )
    
    def _simulate_block_processing(self, start_block: int, end_block: int) -> None:
        """模拟区块处理逻辑"""
        # 模拟不同的处理时间
        processing_delay = 0.1 + (end_block - start_block) * 0.05
        time.sleep(processing_delay)


class MonitorMainLoop:
    """监控主循环示例"""
    
    def __init__(self):
        # 这里需要实际的配置和管理器实例
        self.config = None  # MonitorConfig()
        self.stats_reporter = None  # StatisticsReporter(self.config)
        self.block_processor = None  # BlockProcessor(self.config, self.stats_reporter)
        self.rpc_manager = None
        self.tx_processor = None
        self.confirmation_manager = None
    
    def run_monitoring_with_timing(self) -> None:
        """
        运行监控循环，展示如何测量和记录处理时间
        """
        current_block = 1000000  # 起始区块
        batch_size = 10
        
        while True:  # 实际应用中会有退出条件
            try:
                # 计算本批次的区块范围
                start_block = current_block + 1
                end_block = start_block + batch_size - 1
                
                # 处理区块批次，自动记录时间
                self.block_processor.process_blocks_batch(
                    start_block=start_block,
                    end_block=end_block,
                    rpc_manager=self.rpc_manager,
                    tx_processor=self.tx_processor,
                    confirmation_manager=self.confirmation_manager
                )
                
                current_block = end_block
                
                # 检查是否需要输出详细统计
                if self.stats_reporter.should_log_stats():
                    self.stats_reporter.log_performance_stats(
                        self.rpc_manager,
                        self.tx_processor,
                        self.confirmation_manager
                    )
                
                time.sleep(1)  # 等待下一批次
                
            except KeyboardInterrupt:
                print("停止监控...")
                break
            except Exception as e:
                print(f"处理错误: {e}")
                time.sleep(5)  # 错误后等待
    
    def alternative_timing_approach(self) -> None:
        """
        另一种计时方式：在外部测量处理时间
        """
        # 方法1：简单计时
        start_time = time.time()
        # ... 处理区块逻辑 ...
        processing_time = time.time() - start_time
        
        # 方法2：使用上下文管理器
        with ProcessingTimer() as timer:
            # ... 处理区块逻辑 ...
            pass
        processing_time = timer.elapsed
        
        # 记录进度
        self.stats_reporter.log_processing_progress(
            new_blocks=5,
            current_block=1000005,
            rpc_manager=self.rpc_manager,
            tx_processor=self.tx_processor,
            confirmation_manager=self.confirmation_manager,
            processing_time=processing_time
        )


class ProcessingTimer:
    """处理时间计时器上下文管理器"""
    
    def __init__(self):
        self.start_time: Optional[float] = None
        self.elapsed: float = 0.0
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            self.elapsed = time.time() - self.start_time


def example_usage():
    """使用示例"""
    print("区块处理时间统计示例:")
    print("=" * 50)
    
    # 模拟日志输出格式
    print("不带时间统计的日志:")
    print("📈 处理 10 新区块 | 当前: 1000010 | 待确认: 5 | RPC: 150 (2.5/s) | 缓存: 45/50 | 发现: 8 笔交易")
    
    print("\n带时间统计的日志:")
    print("📈 处理 10 新区块 | 耗时: 1.25s | 速率: 8.0 区块/s | 均时: 0.125s/区块 | 当前: 1000010 | 待确认: 5 | RPC: 150 (2.5/s) | 缓存: 45/50 | 发现: 8 笔交易 | 近期平均: 0.130s/区块")
    
    print("\n最终统计报告中的时间统计:")
    print("🕰️ 区块处理时间统计:")
    print("   处理批次: 247 次")
    print("   总处理时间: 156.78 秒")
    print("   平均处理时间: 0.635 秒/批")
    print("   最快处理时间: 0.234 秒/批")
    print("   最慢处理时间: 2.145 秒/批")
    print("   近期平均时间: 0.598 秒/批")
    print("   平均每区块耗时: 0.0635 秒/区块")
    print("   平均处理速率: 15.7 区块/秒")


if __name__ == "__main__":
    example_usage()
