"""
演示新的多链代币解析器的使用方法
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.token_parser import TokenParser
from config.base_config import ConfigMap, ActiveConfig

def demo_multi_chain_parser():
    """演示多链解析器的功能"""
    
    print("=== EVM 多链代币解析器演示 ===\n")
    
    # 1. 展示所有支持的链
    print("1. 支持的链:")
    for chain_name, config in ConfigMap.items():
        print(f"   - {chain_name}: {config.get('token_name', 'Unknown')} 链")
    print()
    
    # 2. 使用默认解析器（当前活跃链）
    print("2. 默认解析器（当前活跃链）:")
    default_parser = TokenParser()
    print(f"   当前链: {default_parser.chain_name}")
    print(f"   支持的代币: {default_parser.get_supported_tokens()}")
    print()
    
    # 3. 为每个链创建专门的解析器
    print("3. 各链支持的代币详情:")
    for chain_name in ConfigMap.keys():
        parser = TokenParser(chain_name)
        print(f"   === {chain_name.upper()} 链 ===")
        print(f"   原生代币: {ConfigMap[chain_name].get('token_name', 'Unknown')}")
        
        tokens = parser.get_supported_tokens()
        for token in tokens:
            token_info = parser.get_token_info(token)
            if token_info['contract']:
                print(f"   {token}: {token_info['contract']} ({token_info['decimals']} decimals)")
            else:
                print(f"   {token}: 原生代币 ({token_info['decimals']} decimals)")
        print()
    
    # 4. 演示解析功能
    print("4. 模拟解析演示:")
    
    # 创建一个模拟的 USDT 转账交易
    mock_tx = {
        'from': '0x742d35cc6634c0532925a3b8d02d24e88a0a9b42',
        'to': '0x55d398326f99059fF775485246999027B3197955',  # BSC USDT 合约
        'input': '0xa9059cbb000000000000000000000000742d35cc6634c0532925a3b8d02d24e88a0a9b420000000000000000000000000000000000000000000000000000000077359400'
    }
    
    # 使用 BSC 解析器解析
    bsc_parser = TokenParser('bsc')
    result = bsc_parser.parse_usdt_transfer(mock_tx)
    
    if result:
        print("   BSC USDT 转账解析成功:")
        print(f"   - 发送方: {result['from']}")
        print(f"   - 接收方: {result['to']}")
        print(f"   - 金额: {result['amount']} {result['token']}")
        print(f"   - 链: {result['chain']}")
        print(f"   - 格式化金额: {bsc_parser.format_amount(result['amount'], result['token'])}")
    else:
        print("   解析失败")
    
    print()
    
    # 5. 演示跨链切换
    print("5. 演示跨链功能:")
    chains_to_test = ['bsc', 'ethereum', 'polygon']
    
    for chain in chains_to_test:
        if chain in ConfigMap:
            parser = TokenParser(chain)
            print(f"   {chain} 链的 USDT 合约: {parser.get_token_info('USDT')}")

def demo_backward_compatibility():
    """演示向后兼容性"""
    print("\n=== 向后兼容性演示 ===")
    
    # 导入全局函数（保持向后兼容）
    from utils.token_parser import parse_usdt_transfer, get_token_info, format_amount
    
    print("1. 全局函数仍然可用:")
    print(f"   USDT 信息: {get_token_info('USDT')}")
    print(f"   格式化金额: {format_amount(1234567.89, 'USDT')}")
    
    print("\n2. 旧代码无需修改即可运行")

def demo_configuration_flexibility():
    """演示配置的灵活性"""
    print("\n=== 配置灵活性演示 ===")
    
    print("1. 动态添加新链只需修改配置文件")
    print("2. 每个链可以有不同的代币配置")
    print("3. 支持自定义代币")
    
    # 展示自定义代币
    for chain_name, config in ConfigMap.items():
        custom_tokens = config.get('custom_tokens', [])
        if custom_tokens:
            print(f"\n   {chain_name} 链的自定义代币:")
            for token in custom_tokens:
                print(f"   - {token['symbol']}: {token['contract']}")

if __name__ == '__main__':
    try:
        demo_multi_chain_parser()
        demo_backward_compatibility()
        demo_configuration_flexibility()
        
        print("\n=== 演示完成 ===")
        print("新的 TokenParser 已经消除了硬编码，支持多链配置！")
        print("代码是写给人看的，机器只是恰好能运行 - 现在的代码更易读、更灵活！")
        
    except Exception as e:
        print(f"演示过程中出错: {e}")
        import traceback
        traceback.print_exc()
