# EVM转账监控器 - 重构版

> 代码是写给人看的，只是机器恰好可以运行

## 项目结构

重构后的项目按功能模块清晰地组织代码，便于理解和维护：

```
evm_transfer_monitor_refactored/
├── main.py                    # 程序入口点
├── config.yml                 # 配置文件
├── watch_addr.json            # 监控地址列表
│
├── config/                    # 配置模块
│   ├── __init__.py
│   ├── base_config.py         # 基础配置加载
│   └── monitor_config.py      # 监控配置管理
│
├── core/                      # 核心模块
│   ├── __init__.py
│   └── evm_monitor.py         # 主监控器（协调中心）
│
├── models/                    # 数据模型
│   ├── __init__.py
│   └── data_types.py          # 数据类型定义
│
├── managers/                  # 管理器模块
│   ├── __init__.py
│   ├── rpc_manager.py         # RPC调用管理
│   └── confirmation_manager.py # 交易确认管理
│
├── processors/                # 处理器模块
│   ├── __init__.py
│   └── transaction_processor.py # 交易处理器
│
├── utils/                     # 工具模块
│   ├── __init__.py
│   ├── log_utils.py           # 日志工具
│   └── token_parser.py        # 代币解析工具
│
└── reports/                   # 报告模块
    ├── __init__.py
    └── statistics_reporter.py  # 统计报告器
```

## 模块职责

### 📁 config/ - 配置管理
- **base_config.py**: 负责加载和解析YAML配置文件
- **monitor_config.py**: 监控器专用配置类，集中管理所有监控参数

### 📁 core/ - 核心逻辑
- **evm_monitor.py**: 主监控器，协调各个组件，提供统一的监控接口

### 📁 models/ - 数据模型
- **data_types.py**: 定义项目中使用的所有数据结构（TransactionInfo、PerformanceMetrics等）

### 📁 managers/ - 管理器
- **rpc_manager.py**: 管理Web3连接、缓存控制和API调用限制
- **confirmation_manager.py**: 跟踪交易确认状态，管理待确认交易列表

### 📁 processors/ - 处理器
- **transaction_processor.py**: 检测和分析区块链交易，识别大额转账

### 📁 utils/ - 工具类
- **log_utils.py**: 统一的日志管理工具
- **token_parser.py**: ERC-20代币转账解析工具

### 📁 reports/ - 报告模块
- **statistics_reporter.py**: 性能统计和运行状态报告

## 使用方法

### 启动监控器
```bash
cd evm_transfer_monitor_refactored
python main.py
```

### 配置说明
1. 编辑 `config.yml` 设置RPC地址和链信息
2. 修改 `MonitorConfig` 类中的阈值设置
3. 在 `watch_addr.json` 中添加需要监控的地址

## 重构优势

### 🎯 清晰的模块分离
- 每个模块职责单一，便于理解和维护
- 相关功能聚合在同一目录下

### 🔧 易于扩展
- 添加新的代币支持：修改 `token_parser.py`
- 添加新的报告类型：在 `reports/` 下新增模块
- 添加新的处理器：在 `processors/` 下新增模块

### 📦 规范的导入路径
```python
from core.evm_monitor import EVMMonitor
from config.monitor_config import MonitorConfig
from utils.token_parser import TokenParser
```

### 🧪 便于测试
- 每个模块都可以独立测试
- 依赖关系清晰，易于模拟（Mock）

### 🔄 易于维护
- 修改某个功能时，能快速定位到对应模块
- 代码复用性更高
- 符合单一职责原则

## 迁移说明

### 从原版本迁移
1. 将原项目的配置文件复制到新目录
2. 检查import路径是否正确
3. 运行测试确保功能正常

### 配置文件兼容性
- `config.yml` 保持不变
- `watch_addr.json` 保持不变
- 监控逻辑和功能完全一致

## 开发建议

### 添加新功能时
1. 先确定功能属于哪个模块
2. 如果现有模块不合适，创建新的模块
3. 保持模块间的低耦合

### 代码风格
- 遵循"代码是写给人看的"原则
- 添加清晰的注释和文档字符串
- 使用有意义的变量和函数名

## 技术栈

- **Python 3.8+**
- **Web3.py** - 以太坊交互
- **PyYAML** - 配置文件解析
- **asyncio** - 异步编程

## 许可证

MIT License
