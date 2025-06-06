"""
链配置工具 - 获取不同链的确认数等配置参数
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.base_config import ConfigMap, ActiveConfig
from utils.log_utils import get_logger

logger = get_logger(__name__)

class ChainConfig:
    """链配置管理器"""
    
    @classmethod
    def get_confirmation_blocks(cls, chain_name=None, amount=0, token_symbol='USDT'):
        """
        获取指定链的确认数
        
        Args:
            chain_name: 链名称，如果不指定则使用活跃链
            amount: 交易金额，用于判断是否需要额外确认
            token_symbol: 代币符号，用于判断高风险阈值
            
        Returns:
            int: 需要的确认数
        """
        from config.base_config import _loaded_config
        
        # 获取链配置
        if chain_name:
            chain_config = ConfigMap.get(chain_name, {})
        else:
            chain_config = ActiveConfig
            chain_name = cls._get_active_chain_name()
        
        # 获取基础确认数
        base_confirmations = chain_config.get('confirmation_blocks')
        
        # 如果没有配置，使用默认值
        if base_confirmations is None:
            monitor_config = _loaded_config.get('monitor', {}) if _loaded_config else {}
            base_confirmations = monitor_config.get('default_confirmation_blocks', 10)
        
        # 检查是否是高风险交易
        extra_confirmations = cls._get_extra_confirmations_for_high_value(
            amount, token_symbol, _loaded_config
        )
        
        total_confirmations = base_confirmations + extra_confirmations
        
        if extra_confirmations > 0:
            logger.info(f"高风险交易 {amount} {token_symbol}，使用额外确认数: {base_confirmations} + {extra_confirmations} = {total_confirmations}")
        
        return total_confirmations
    
    @classmethod
    def _get_extra_confirmations_for_high_value(cls, amount, token_symbol, config_data):
        """获取高风险交易的额外确认数"""
        if not config_data:
            return 0
            
        monitor_config = config_data.get('monitor', {})
        high_value_thresholds = monitor_config.get('high_value_thresholds', {})
        
        # 获取该代币的高风险阈值
        threshold = high_value_thresholds.get(token_symbol)
        if threshold is None:
            threshold = high_value_thresholds.get('default', float('inf'))
        
        # 如果超过阈值，返回额外确认数
        if amount >= threshold:
            return monitor_config.get('high_value_extra_confirmations', 5)
        
        return 0
    
    @classmethod
    def _get_active_chain_name(cls):
        """获取当前活跃链的名称"""
        for chain_name, config in ConfigMap.items():
            if config == ActiveConfig:
                return chain_name
        return "unknown"
    
    @classmethod
    def get_block_time(cls, chain_name=None):
        """
        获取指定链的出块时间
        
        Args:
            chain_name: 链名称，如果不指定则使用活跃链
            
        Returns:
            int: 出块时间(秒)
        """
        if chain_name:
            chain_config = ConfigMap.get(chain_name, {})
        else:
            chain_config = ActiveConfig
        
        return chain_config.get('block_time', 12)  # 默认12秒
    
    @classmethod
    def get_l1_finality_blocks(cls, chain_name=None):
        """
        获取L2链等待L1最终确认的区块数
        
        Args:
            chain_name: 链名称，如果不指定则使用活跃链
            
        Returns:
            int: L1最终确认区块数，如果不是L2链则返回None
        """
        if chain_name:
            chain_config = ConfigMap.get(chain_name, {})
        else:
            chain_config = ActiveConfig
        
        return chain_config.get('l1_finality_blocks')
    
    @classmethod
    def is_layer2_chain(cls, chain_name=None):
        """
        检查是否为Layer2链
        
        Args:
            chain_name: 链名称，如果不指定则使用活跃链
            
        Returns:
            bool: 是否为L2链
        """
        return cls.get_l1_finality_blocks(chain_name) is not None
    
    @classmethod
    def get_estimated_confirmation_time(cls, chain_name=None, amount=0, token_symbol='USDT'):
        """
        估算确认时间
        
        Args:
            chain_name: 链名称
            amount: 交易金额
            token_symbol: 代币符号
            
        Returns:
            dict: 包含确认时间信息的字典
        """
        confirmations = cls.get_confirmation_blocks(chain_name, amount, token_symbol)
        block_time = cls.get_block_time(chain_name)
        l1_finality = cls.get_l1_finality_blocks(chain_name)
        
        # 基础确认时间
        base_time = confirmations * block_time
        
        result = {
            'confirmations': confirmations,
            'block_time': block_time,
            'estimated_time_seconds': base_time,
            'estimated_time_minutes': base_time / 60,
            'is_layer2': cls.is_layer2_chain(chain_name)
        }
        
        # 如果是L2链，还需要等待L1最终确认
        if l1_finality:
            l1_time = l1_finality * 12  # Ethereum块时间约12秒
            result['l1_finality_blocks'] = l1_finality
            result['l1_finality_time_seconds'] = l1_time
            result['l1_finality_time_minutes'] = l1_time / 60
            result['total_time_seconds'] = base_time + l1_time
            result['total_time_minutes'] = (base_time + l1_time) / 60
        else:
            result['total_time_seconds'] = base_time
            result['total_time_minutes'] = base_time / 60
        
        return result
    
    @classmethod
    def get_chain_summary(cls):
        """获取所有链的配置摘要"""
        summary = {}
        
        for chain_name, config in ConfigMap.items():
            summary[chain_name] = {
                'token_name': config.get('token_name', 'Unknown'),
                'chain_id': config.get('chain_id'),
                'confirmation_blocks': config.get('confirmation_blocks', 'Not configured'),
                'block_time': config.get('block_time', 'Not configured'),
                'is_layer2': cls.is_layer2_chain(chain_name),
                'l1_finality_blocks': config.get('l1_finality_blocks')
            }
        
        return summary


if __name__ == '__main__':
    # 演示不同链的确认数配置
    print("=== 链配置演示 ===\n")
    
    # 1. 显示所有链的配置摘要
    print("1. 所有链的配置摘要:")
    summary = ChainConfig.get_chain_summary()
    for chain_name, info in summary.items():
        print(f"   {chain_name}:")
        print(f"     原生代币: {info['token_name']}")
        print(f"     确认数: {info['confirmation_blocks']}")
        print(f"     出块时间: {info['block_time']}秒")
        print(f"     是否L2: {info['is_layer2']}")
        if info['l1_finality_blocks']:
            print(f"     L1最终确认: {info['l1_finality_blocks']}")
        print()
    
    # 2. 演示不同金额的确认数
    print("2. 不同金额的确认数演示:")
    test_amounts = [1000, 50000, 150000]  # 小额、中等、大额
    
    for chain_name in ['bsc', 'ethereum', 'polygon', 'arbitrum']:
        if chain_name in ConfigMap:
            print(f"   {chain_name} 链:")
            for amount in test_amounts:
                confirmations = ChainConfig.get_confirmation_blocks(chain_name, amount, 'USDT')
                time_info = ChainConfig.get_estimated_confirmation_time(chain_name, amount, 'USDT')
                print(f"     {amount} USDT: {confirmations}确认 (~{time_info['total_time_minutes']:.1f}分钟)")
            print()
    
    print("=== 演示完成 ===")
    print("现在不同的链使用不同的确认数，更加安全和高效！")
