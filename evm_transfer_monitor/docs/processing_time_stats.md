# 区块处理时间统计功能

## 概述

在 `StatisticsReporter.log_processing_progress` 函数中新增了区块处理时间统计功能，能够记录和分析每批区块的处理性能。

## 主要改进

### 1. 新增参数
```python
def log_processing_progress(self, new_blocks: int, current_block: int, 
                         rpc_manager: RPCManager, tx_processor: TransactionProcessor, 
                         confirmation_manager: ConfirmationManager, 
                         processing_time: float = None) -> None:
```

新增了 `processing_time` 可选参数，用于传入处理这批区块所花费的时间（秒）。

### 2. 新增统计信息
- **耗时**: 本批次处理总时间
- **速率**: 区块处理速率（区块/秒）
- **均时**: 每个区块平均处理时间
- **近期平均**: 最近10次处理的平均时间

### 3. 内部状态跟踪
- 保存最近50次的处理时间记录
- 跟踪最大、最小、平均处理时间
- 计算近期性能趋势

## 使用方法

### 基本使用
```python
import time

# 记录开始时间
start_time = time.time()

# 处理区块逻辑
process_blocks(start_block, end_block)

# 计算处理时间
processing_time = time.time() - start_time

# 记录进度（包含时间统计）
stats_reporter.log_processing_progress(
    new_blocks=10,
    current_block=current_block,
    rpc_manager=rpc_manager,
    tx_processor=tx_processor,
    confirmation_manager=confirmation_manager,
    processing_time=processing_time  # 传入处理时间
)
```

### 使用上下文管理器
```python
from examples.processing_time_example import ProcessingTimer

with ProcessingTimer() as timer:
    # 处理区块逻辑
    process_blocks(start_block, end_block)

# 记录进度
stats_reporter.log_processing_progress(
    new_blocks=10,
    current_block=current_block,
    rpc_manager=rpc_manager,
    tx_processor=tx_processor,
    confirmation_manager=confirmation_manager,
    processing_time=timer.elapsed
)
```

## 日志输出示例

### 不带时间统计（原有格式）
```
📈 处理 10 新区块 | 当前: 1000010 | 待确认: 5 | RPC: 150 (2.5/s) | 缓存: 45/50 | 发现: 8 笔交易
```

### 带时间统计（新格式）
```
📈 处理 10 新区块 | 耗时: 1.25s | 速率: 8.0 区块/s | 均时: 0.125s/区块 | 当前: 1000010 | 待确认: 5 | RPC: 150 (2.5/s) | 缓存: 45/50 | 发现: 8 笔交易 | 近期平均: 0.130s/区块
```

## 最终统计报告

在程序结束时，`log_final_stats` 会输出详细的处理时间分析：

```
🕰️ 区块处理时间统计:
   处理批次: 247 次
   总处理时间: 156.78 秒
   平均处理时间: 0.635 秒/批
   最快处理时间: 0.234 秒/批
   最慢处理时间: 2.145 秒/批
   近期平均时间: 0.598 秒/批
   平均每区块耗时: 0.0635 秒/区块
   平均处理速率: 15.7 区块/秒
```

## 新增的公共方法

### `get_processing_time_stats()`
返回详细的处理时间统计数据：
```python
{
    'count': 247,                    # 处理批次数
    'total_time': 156.78,           # 总处理时间
    'avg_time': 0.635,              # 平均处理时间
    'min_time': 0.234,              # 最快处理时间
    'max_time': 2.145,              # 最慢处理时间
    'recent_avg': 0.598             # 近期平均时间
}
```

## 兼容性

- **向后兼容**: `processing_time` 参数是可选的，不传入时保持原有行为
- **渐进式采用**: 可以在部分调用点先添加时间统计，逐步完善
- **零影响**: 对现有代码无任何破坏性改动

## 性能考虑

- 内存占用: 最多保存50次处理时间记录（约200字节）
- 计算开销: 仅在有时间数据时进行简单的算术运算
- 日志开销: 适度增加日志长度，但信息密度更高

## 示例代码

详细的使用示例请参考：`examples/processing_time_example.py`
