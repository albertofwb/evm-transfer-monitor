import yaml
import os
from typing import Dict, Any, Optional


def _load_config(config_path: str = "config.yml") -> Optional[Dict[str, Any]]:
    """
    内部函数：加载并解析 YAML 配置文件。
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        配置字典或 None（如果加载失败）
    """
    # 如果是相对路径，则相对于项目根目录
    if not os.path.isabs(config_path):
        # 获取当前文件所在目录的上一级目录（项目根目录）
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        config_path = os.path.join(project_root, config_path)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        return config_data
    except FileNotFoundError:
        print(f"Warning: Config file not found at {config_path}. Using default configuration.")
        return None
    except yaml.YAMLError as exc:
        print(f"Error parsing YAML file: {exc}. Using default configuration.")
        return None


# 在模块加载时执行配置加载和解析
_loaded_config = _load_config()
_active_chain = _loaded_config.get('active_chain', 'core') if _loaded_config else 'core'

# 全局变量，用于存储当前活跃链的配置
ConfigMap = _loaded_config.get('chains', {}) if _loaded_config else {}
ActiveConfig = ConfigMap.get(_active_chain, {}) if ConfigMap else {}

# 监控配置
MonitorConfig = _loaded_config.get('monitor', {}) if _loaded_config else {}

# 日志配置  
LoggingConfig = _loaded_config.get('logging', {}) if _loaded_config else {}

# RabbitMQ 配置（保留原始配置数据，供各个实例使用）
_RabbitMQConfigData = _loaded_config.get('rabbitmq', {}) if _loaded_config else {}


def get_rabbitmq_config() -> Dict[str, Any]:
    """
    获取 RabbitMQ 完整配置
    
    Returns:
        RabbitMQ 配置字典
    """
    return {
        # 连接配置
        'host': _RabbitMQConfigData.get('host', 'localhost'),
        'port': _RabbitMQConfigData.get('port', 5672),
        'username': _RabbitMQConfigData.get('username', 'guest'),
        'password': _RabbitMQConfigData.get('password', 'guest'),
        'virtual_host': _RabbitMQConfigData.get('virtual_host', '/'),
        'heartbeat': _RabbitMQConfigData.get('heartbeat', 600),
        'connection_timeout': _RabbitMQConfigData.get('connection_timeout', 30),
        
        # 钱包更新队列配置
        'wallet_updates': _RabbitMQConfigData.get('wallet_updates', {
            'exchange_name': 'wallet_updates',
            'exchange_type': 'fanout',
            'queue_name': '',
            'durable_queue': False,
            'auto_delete_queue': True,
            'exclusive_queue': True,
            'prefetch_count': 1
        }),
        
        # 启用状态
        'enabled': _RabbitMQConfigData.get('enabled', True),
        
        # 重连配置
        'reconnect': _RabbitMQConfigData.get('reconnect', {
            'max_retries': 5,
            'retry_delay': 5,
            'backoff_multiplier': 2
        })
    }



if __name__ == "__main__":
    print("\n--- ConfigMap (所有链的配置) ---")
    for chain_name, config in ConfigMap.items():
        print(f"Chain: {chain_name}")
        for key, value in config.items():
            print(f"  {key}: {value}")

    print("--- ActiveConfig ---")
    for key, value in ActiveConfig.items():
        print(f"  {key}: {value}")
