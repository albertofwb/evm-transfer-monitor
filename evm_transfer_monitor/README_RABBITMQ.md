# RabbitMQ 钱包地址更新通知系统

## 概述

这个系统实现了基于 RabbitMQ 消息队列的钱包地址更新通知功能，当有新的钱包地址需要监控时，通过消息队列异步通知监控系统添加到监控列表中。

## 系统架构

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   消息生产者     │────▶│   RabbitMQ   │────▶│   EVM 监控器    │
│ (外部系统)      │     │   消息队列    │     │  (消费者)       │
└─────────────────┘     └──────────────┘     └─────────────────┘
                              │
                              ▼
                        ┌──────────────┐
                        │ 钱包地址监控  │
                        │     列表      │
                        └──────────────┘
```

## 消息格式

### 钱包地址更新消息

```json
{
    "address": "0x1234567890abcdef1234567890abcdef12345678"
}
```

### 可选字段

```json
{
    "address": "0x1234567890abcdef1234567890abcdef12345678",
    "timestamp": 1640995200,
    "priority": "high",
    "source": "user_input"
}
```

## 配置说明

### 1. 配置文件修改

在 `config.yml` 中添加 RabbitMQ 配置：

```yaml
# RabbitMQ 配置
rabbitmq:
  # 连接配置
  host: "localhost"
  port: 5672
  username: "guest"
  password: "guest"
  
  # 虚拟主机
  virtual_host: "/"
  
  # 连接选项
  heartbeat: 600
  connection_timeout: 30
  
  # 钱包地址更新队列配置
  wallet_updates:
    exchange_name: "wallet_updates"
    exchange_type: "fanout"
    queue_name: ""  # 空字符串表示自动生成队列名
    durable_queue: false
    auto_delete_queue: true
    exclusive_queue: true
    prefetch_count: 1
  
  # 是否启用 RabbitMQ 钱包地址更新监听
  enabled: true
  
  # 重连配置
  reconnect:
    max_retries: 5
    retry_delay: 5
    backoff_multiplier: 2
```

### 2. 配置参数说明

#### 连接配置
- `host`: RabbitMQ 服务器地址
- `port`: RabbitMQ 端口（默认 5672）
- `username/password`: 认证信息
- `virtual_host`: 虚拟主机路径

#### 队列配置
- `exchange_name`: 交换机名称
- `exchange_type`: 交换机类型（fanout/topic/direct）
- `queue_name`: 队列名称（空则自动生成）
- `durable_queue`: 队列是否持久化
- `auto_delete_queue`: 是否自动删除队列
- `exclusive_queue`: 是否为独占队列
- `prefetch_count`: 预取消息数量

#### 重连配置
- `max_retries`: 最大重连次数
- `retry_delay`: 重连延迟（秒）
- `backoff_multiplier`: 延迟倍数

## 使用方法

### 1. 启动监控系统

```python
from core.evm_monitor import EVMMonitor
from config.monitor_config import MonitorConfig
from utils.token_parser import TokenParser

# 创建配置和监控器
config = MonitorConfig.from_chain_name('bsc')
token_parser = TokenParser(config)
monitor = EVMMonitor(config, token_parser)

# 启动监控（会自动初始化 RabbitMQ）
await monitor.start_monitoring()
```

### 2. 发送钱包地址更新消息

#### 使用提供的测试工具

```bash
# 发送单个消息
python tests/test_rabbitmq_producer.py single

# 发送批量消息
python tests/test_rabbitmq_producer.py batch

# 交互式发送
python tests/test_rabbitmq_producer.py interactive

# 运行所有测试
python tests/test_rabbitmq_producer.py
```

#### 使用代码发送

```python
from tests.test_rabbitmq_producer import AsyncRabbitMQProducer

# 配置生产者
config = {
    'host': 'localhost',
    'port': 5672,
    'username': 'guest',
    'password': 'guest',
    'exchange_name': 'wallet_updates',
    'exchange_type': 'fanout'
}

# 发送消息
async with AsyncRabbitMQProducer(**config) as producer:
    await producer.send_wallet_update(
        "0x1234567890abcdef1234567890abcdef12345678"
    )
```

### 3. 外部系统集成

外部系统可以通过任何 RabbitMQ 客户端发送消息：

#### Python (pika)
```python
import pika
import json

connection = pika.BlockingConnection(
    pika.ConnectionParameters('localhost')
)
channel = connection.channel()

# 声明交换机
channel.exchange_declare(
    exchange='wallet_updates', 
    exchange_type='fanout',
    durable=True
)

# 发送消息
message = {"address": "0x1234567890abcdef1234567890abcdef12345678"}
channel.basic_publish(
    exchange='wallet_updates',
    routing_key='',
    body=json.dumps(message)
)

connection.close()
```

#### Node.js (amqplib)
```javascript
const amqp = require('amqplib');

async function sendWalletUpdate(address) {
    const connection = await amqp.connect('amqp://localhost');
    const channel = await connection.createChannel();
    
    const exchange = 'wallet_updates';
    await channel.assertExchange(exchange, 'fanout', { durable: true });
    
    const message = { address: address };
    channel.publish(exchange, '', Buffer.from(JSON.stringify(message)));
    
    await connection.close();
}

sendWalletUpdate('0x1234567890abcdef1234567890abcdef12345678');
```

#### curl (通过 RabbitMQ HTTP API)
```bash
curl -i -u guest:guest -H "content-type:application/json" \
  -X POST http://localhost:15672/api/exchanges/%2f/wallet_updates/publish \
  -d '{"properties":{},"routing_key":"","payload":"{\"address\":\"0x1234567890abcdef1234567890abcdef12345678\"}","payload_encoding":"string"}'
```

## 功能特性

### 1. 异步处理
- 完全基于 async/await 的异步实现
- 非阻塞消息处理
- 高并发支持

### 2. 可靠性保证
- 自动重连机制
- 消息确认机制
- 错误处理和重试

### 3. 灵活配置
- 支持多种交换机类型
- 可配置队列参数
- 动态启用/禁用

### 4. 监控支持
- 连接状态监控
- 消息处理统计
- 健康状态检查

## 状态监控

### 获取 RabbitMQ 状态

```python
# 获取完整健康状态（包含 RabbitMQ）
health_status = await monitor.get_health_status()

print(f"RabbitMQ 启用: {health_status['rabbitmq_enabled']}")
print(f"RabbitMQ 健康: {health_status['rabbitmq_healthy']}")

if 'rabbitmq_status' in health_status:
    rabbitmq_status = health_status['rabbitmq_status']
    print(f"连接状态: {rabbitmq_status['consumer_status']['connected']}")
    print(f"消费状态: {rabbitmq_status['consumer_status']['consuming']}")
    print(f"处理统计: {rabbitmq_status['handler_stats']}")
```

### 监控指标

- `rabbitmq_enabled`: 是否启用 RabbitMQ
- `rabbitmq_healthy`: RabbitMQ 是否健康
- `connected`: 是否连接到 RabbitMQ
- `consuming`: 是否正在消费消息
- `processed_count`: 已处理的消息数量

## 故障排除

### 1. 连接问题

**问题**: 无法连接到 RabbitMQ
```
❌ 连接到 RabbitMQ 失败: [Errno 111] Connection refused
```

**解决方案**:
- 确认 RabbitMQ 服务已启动
- 检查主机和端口配置
- 验证用户名密码

### 2. 权限问题

**问题**: 认证失败
```
❌ 连接到 RabbitMQ 失败: ACCESS_REFUSED
```

**解决方案**:
- 检查用户名密码
- 确认用户有足够权限
- 检查虚拟主机配置

### 3. 消息格式问题

**问题**: 消息处理失败
```
⚠️ 消息格式无效: {'invalid_field': 'value'}
```

**解决方案**:
- 确保消息包含 'address' 字段
- 验证地址格式（0x + 40位十六进制）
- 检查 JSON 格式

### 4. 重连问题

**问题**: 频繁重连
```
🔄 检测到 RabbitMQ 连接断开，尝试重连...
```

**解决方案**:
- 检查网络稳定性
- 调整心跳间隔
- 增加重连延迟

## 最佳实践

### 1. 生产环境配置

```yaml
rabbitmq:
  host: "rabbitmq-cluster.internal"
  port: 5672
  username: "monitor_user"
  password: "${RABBITMQ_PASSWORD}"
  virtual_host: "/monitor"
  
  wallet_updates:
    exchange_name: "wallet_updates"
    exchange_type: "topic"  # 使用 topic 类型更灵活
    durable_queue: true     # 生产环境建议持久化
    auto_delete_queue: false
    exclusive_queue: false
    
  reconnect:
    max_retries: 10
    retry_delay: 10
    backoff_multiplier: 1.5
```

### 2. 性能优化

- 设置合适的 `prefetch_count`
- 使用连接池（如果需要）
- 批量处理消息
- 监控队列长度

### 3. 安全考虑

- 使用专用用户账号
- 限制用户权限
- 启用 TLS 加密
- 网络隔离

### 4. 监控告警

```python
# 设置告警条件
async def check_rabbitmq_health():
    status = await monitor.get_health_status()
    
    if not status['rabbitmq_healthy']:
        # 发送告警
        send_alert("RabbitMQ 连接异常")
    
    if status.get('rabbitmq_status', {}).get('handler_stats', {}).get('processed_count', 0) == 0:
        # 长时间无消息处理
        send_alert("RabbitMQ 消息处理停滞")
```

## 扩展功能

### 1. 消息优先级

可以扩展消息格式支持优先级：

```json
{
    "address": "0x1234567890abcdef1234567890abcdef12345678",
    "priority": "high"
}
```

### 2. 批量地址

支持批量添加地址：

```json
{
    "addresses": [
        "0x1234567890abcdef1234567890abcdef12345678",
        "0xabcdef1234567890abcdef1234567890abcdef12"
    ]
}
```

### 3. 地址分类

支持不同类型的地址监控：

```json
{
    "address": "0x1234567890abcdef1234567890abcdef12345678",
    "type": "vip_user",
    "threshold": 10000
}
```

## 部署建议

### 1. Docker 部署

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "-m", "core.evm_monitor"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  rabbitmq:
    image: rabbitmq:3-management
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      RABBITMQ_DEFAULT_USER: monitor
      RABBITMQ_DEFAULT_PASS: monitor_password
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
      
  evm_monitor:
    build: .
    depends_on:
      - rabbitmq
    environment:
      RABBITMQ_HOST: rabbitmq
      RABBITMQ_USER: monitor
      RABBITMQ_PASS: monitor_password
    volumes:
      - ./config.yml:/app/config.yml
      - ./logs:/app/logs

volumes:
  rabbitmq_data:
```

### 2. Kubernetes 部署

```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: evm-monitor
spec:
  replicas: 1
  selector:
    matchLabels:
      app: evm-monitor
  template:
    metadata:
      labels:
        app: evm-monitor
    spec:
      containers:
      - name: evm-monitor
        image: your-registry/evm-monitor:latest
        env:
        - name: RABBITMQ_HOST
          value: "rabbitmq-service"
        - name: RABBITMQ_USER
          valueFrom:
            secretKeyRef:
              name: rabbitmq-secret
              key: username
        - name: RABBITMQ_PASS
          valueFrom:
            secretKeyRef:
              name: rabbitmq-secret
              key: password
        volumeMounts:
        - name: config-volume
          mountPath: /app/config.yml
          subPath: config.yml
      volumes:
      - name: config-volume
        configMap:
          name: evm-monitor-config
```

## 总结

本系统实现了完整的异步 RabbitMQ 钱包地址更新通知功能，具有以下特点：

✅ **完全异步**: 基于 async/await 的异步实现  
✅ **高可靠性**: 自动重连、消息确认、错误处理  
✅ **灵活配置**: 支持多种部署场景和配置选项  
✅ **生产就绪**: 包含监控、日志、健康检查等功能  
✅ **易于集成**: 标准的 RabbitMQ 协议，支持多语言客户端  
✅ **测试完善**: 提供完整的测试工具和示例代码  

通过这个系统，您可以实现：
- 实时接收钱包地址更新通知
- 自动将新地址添加到监控列表
- 支持高并发的地址添加操作
- 可靠的消息传递和处理机制

系统已经完全集成到现有的 EVM 监控器中，只需要启用 RabbitMQ 配置即可开始使用。
