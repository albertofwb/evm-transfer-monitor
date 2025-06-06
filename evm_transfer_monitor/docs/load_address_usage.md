# 钱包地址加载工具使用说明

## 功能概述

`load_address.py` 提供了从 JSON 配置文件加载以太坊钱包地址的功能，代码简洁易懂，专注于解决实际问题。

## 主要功能

### 1. 加载钱包地址
```python
from utils.load_address import load_wallet_addresses

# 使用默认配置文件路径
addresses = load_wallet_addresses()

# 或指定自定义路径
addresses = load_wallet_addresses("/path/to/custom/config.json")
```

### 2. 获取地址数量
```python
from utils.load_address import get_address_count

count = get_address_count()
print(f"共有 {count} 个地址需要监控")
```

### 3. 验证地址格式
```python
from utils.load_address import validate_address

is_valid = validate_address("0x5bdf85216ec1e38d6458c870992a69e38e03f7ef")
```

## 配置文件格式

配置文件 `watch_addr.json` 采用标准 JSON 格式：

```json
{
  "evm_wallet_addresses": [
    "0x5bdf85216ec1e38D6458C870992A69e38e03F7Ef",
    "0x12A4aBcAD8177B7763594D4AF7066c58B6f897Fb"
  ]
}
```

## 特性

- **自动路径解析**: 无需手动指定配置文件路径
- **地址格式验证**: 自动检查以太坊地址格式的正确性
- **统一小写处理**: 地址统一转换为小写格式，避免大小写问题
- **友好的错误提示**: 清晰的异常信息帮助快速定位问题
- **灵活的使用方式**: 支持默认路径和自定义路径

## 错误处理

工具会自动处理常见错误：
- 配置文件不存在
- JSON 格式错误
- 地址格式不正确
- 空的地址列表

## 使用示例

运行测试：
```bash
python utils/load_address.py
```

查看完整示例：
```bash
python example_usage.py
```

这个工具设计遵循"代码是写给人看的"原则，每个函数都有清晰的目的和简洁的实现。
