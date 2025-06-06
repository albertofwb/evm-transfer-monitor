"""
地址加载工具 - 负责从配置文件中读取钱包地址
"""

import json
import os
from typing import List, Optional
from pathlib import Path


def load_wallet_addresses(config_path: Optional[str] = None) -> List[str]:
    """
    从配置文件加载钱包地址列表
    
    参数:
        config_path: 配置文件路径，如果为空则使用默认路径
    
    返回:
        钱包地址列表
    
    异常:
        FileNotFoundError: 配置文件不存在
        ValueError: 配置文件格式错误或地址列表为空
    """
    # 确定配置文件路径
    if config_path is None:
        # 获取项目根目录路径
        current_dir = Path(__file__).parent.parent
        config_path = current_dir / "watch_addr.json"
    
    # 检查文件是否存在
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    try:
        # 读取并解析JSON文件
        with open(config_path, 'r', encoding='utf-8') as file:
            config_data = json.load(file)
        
        # 获取地址列表
        addresses = config_data.get('evm_wallet_addresses', [])
        
        if not addresses:
            raise ValueError("配置文件中未找到有效的钱包地址")
        
        # 验证地址格式（简单验证以太坊地址格式）
        valid_addresses = []
        for addr in addresses:
            if isinstance(addr, str) and addr.startswith('0x') and len(addr) == 42:
                valid_addresses.append(addr.lower())  # 统一转为小写
            else:
                print(f"警告: 跳过无效地址格式 {addr}")
        
        if not valid_addresses:
            raise ValueError("未找到格式正确的钱包地址")
        
        print(f"成功加载 {len(valid_addresses)} 个钱包地址")
        return valid_addresses
        
    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件JSON格式错误: {e}")
    except Exception as e:
        raise ValueError(f"读取配置文件时发生错误: {e}")


def get_address_count(config_path: Optional[str] = None) -> int:
    """
    获取配置文件中的地址数量，不加载完整列表
    
    参数:
        config_path: 配置文件路径
    
    返回:
        地址数量
    """
    try:
        addresses = load_wallet_addresses(config_path)
        return len(addresses)
    except Exception:
        return 0


def validate_address(address: str) -> bool:
    """
    验证单个以太坊地址格式
    
    参数:
        address: 待验证的地址
    
    返回:
        地址格式是否正确
    """
    return (isinstance(address, str) and 
            address.startswith('0x') and 
            len(address) == 42 and 
            all(c in '0123456789abcdefABCDEF' for c in address[2:]))


if __name__ == "__main__":
    # 测试加载功能
    try:
        addresses = load_wallet_addresses()
        print(f"加载的地址列表:")
        for i, addr in enumerate(addresses[:5], 1):  # 只显示前5个
            print(f"  {i}. {addr}")
        
        if len(addresses) > 5:
            print(f"  ... 还有 {len(addresses) - 5} 个地址")
            
    except Exception as e:
        print(f"加载失败: {e}")
