import yaml


def _load_config(config_path="config.yml"):
    """
    内部函数：加载并解析 YAML 配置文件。
    """
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



if __name__ == "__main__":
    print("\n--- ConfigMap (所有链的配置) ---")
    for chain_name, config in ConfigMap.items():
        print(f"Chain: {chain_name}")
        for key, value in config.items():
            print(f"  {key}: {value}")

    print("--- ActiveConfig ---")
    for key, value in ActiveConfig.items():
        print(f"  {key}: {value}")
