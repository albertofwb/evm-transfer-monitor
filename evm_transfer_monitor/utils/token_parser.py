"""
改进的代币转账解析辅助方法
用于解析 ERC-20 代币的转账交易，增强了对不规范数据的处理能力
"""

from utils.log_utils import get_logger
import re

logger = get_logger(__name__)

class TokenParser:
    """代币转账解析器 - 改进版"""
    
    # 常用代币合约地址 (BSC网络)
    CONTRACTS = {
        'USDT': '0x55d398326f99059fF775485246999027B3197955',
        'USDC': '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d', 
        'BUSD': '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56',
        'BNB': None  # 原生代币，不是合约
    }
    
    # 代币小数位数
    DECIMALS = {
        'USDT': 18,  # BSC上的USDT是18位小数
        'USDC': 18,
        'BUSD': 18,
        'BNB': 18
    }
    
    # ERC-20 方法签名
    TRANSFER_SIGNATURE = '0xa9059cbb'  # transfer(address,uint256)
    
    @classmethod
    def parse_erc20_transfer(cls, tx, token_symbol='USDT'):
        """
        解析 ERC-20 代币转账交易 - 改进版，能处理不规范的input数据
        
        Args:
            tx: 交易对象
            token_symbol: 代币符号，默认 USDT
            
        Returns:
            dict: 包含转账信息的字典，解析失败返回 None
        """
        if token_symbol not in cls.CONTRACTS:
            logger.debug(f"不支持的代币类型: {token_symbol}")
            return None
            
        contract_address = cls.CONTRACTS[token_symbol]
        if not contract_address:
            logger.debug(f"{token_symbol} 是原生代币，不需要解析合约调用")
            return None
            
        # 基本检查
        if not tx.get('to') or tx['to'].lower() != contract_address.lower():
            return None
            
        if not tx.get('input'):
            return None
        
        # 规范化input数据 - 处理字节和字符串两种情况
        input_data = tx['input']
        
        # 如果是字节对象，转换为十六进制字符串
        if isinstance(input_data, bytes):
            input_data = input_data.hex()
            if not input_data.startswith('0x'):
                input_data = '0x' + input_data
        else:
            # 如果是字符串，进行常规处理
            input_data = input_data.strip()
            if not input_data.startswith('0x'):
                input_data = '0x' + input_data
        
        # 移除'0x'前缀进行处理
        hex_data = input_data[2:]
        
        # 检查最小长度：方法签名(8) + 至少一个参数(64) = 72
        if len(hex_data) < 72:
            logger.debug(f"Input数据太短: {len(hex_data)} < 72")
            return None
        
        # 检查方法签名
        if hex_data[:8].lower() != cls.TRANSFER_SIGNATURE[2:].lower():
            logger.debug(f"方法签名不匹配: {hex_data[:8]} != {cls.TRANSFER_SIGNATURE[2:]}")
            return None
        
        try:
            # 解析接收地址（第1个参数）
            if len(hex_data) < 72:  # 8 + 64
                logger.debug("数据长度不足以包含完整的地址参数")
                return None
                
            address_param = hex_data[8:72]  # 64字符参数
            # 地址参数的前24个字符应该是0填充，后40个字符是实际地址
            to_address = '0x' + address_param[24:64]
            
            # 解析转账金额（第2个参数）
            amount_wei = 0
            if len(hex_data) >= 136:  # 完整的第二个参数
                amount_hex = hex_data[72:136]
            elif len(hex_data) > 72:  # 不完整的第二个参数，尝试解析
                amount_hex = hex_data[72:].ljust(64, '0')  # 右侧补0
                logger.debug(f"金额参数不完整，补0后处理: {amount_hex}")
            else:
                logger.debug("没有金额参数")
                return None
            
            # 解析金额
            amount_wei = int(amount_hex, 16)
            decimals = cls.DECIMALS.get(token_symbol, 18)
            amount = amount_wei / (10 ** decimals)
            
            # 验证地址格式
            if not cls._is_valid_address(to_address):
                logger.debug(f"解析出的地址格式不正确: {to_address}")
                return None
            
            return {
                'from': tx['from'],
                'to': to_address.lower(),
                'amount': amount,
                'token': token_symbol,
                'contract': contract_address.lower(),
                'raw_amount_wei': amount_wei
            }
            
        except (ValueError, IndexError) as e:
            logger.debug(f"解析{token_symbol}转账失败: {e}, input_data类型: {type(tx.get('input'))}, 长度: {len(str(tx.get('input', '')))}")
            return None
        except Exception as e:
            logger.error(f"解析{token_symbol}转账发生未预期错误: {e}, input数据: {tx.get('input', 'N/A')[:100]}...")
            return None
    
    @classmethod
    def _is_valid_address(cls, address):
        """验证以太坊地址格式"""
        if not address or len(address) != 42:
            return False
        if not address.startswith('0x'):
            return False
        # 检查是否为有效的十六进制
        try:
            int(address[2:], 16)
            return True
        except ValueError:
            return False
    
    @classmethod
    def parse_usdt_transfer(cls, tx):
        """解析 USDT 转账（快捷方法）"""
        return cls.parse_erc20_transfer(tx, 'USDT')
    
    @classmethod
    def parse_usdc_transfer(cls, tx):
        """解析 USDC 转账（快捷方法）"""
        return cls.parse_erc20_transfer(tx, 'USDC')
    
    @classmethod
    def parse_busd_transfer(cls, tx):
        """解析 BUSD 转账（快捷方法）"""
        return cls.parse_erc20_transfer(tx, 'BUSD')
    
    @classmethod
    def is_token_contract(cls, address):
        """检查地址是否为支持的代币合约"""
        if not address:
            return False
        address = address.lower()
        for token, contract in cls.CONTRACTS.items():
            if contract and contract.lower() == address:
                return token
        return None
    
    @classmethod
    def get_token_info(cls, token_symbol):
        """获取代币信息"""
        if token_symbol not in cls.CONTRACTS:
            return None
        return {
            'symbol': token_symbol,
            'contract': cls.CONTRACTS[token_symbol],
            'decimals': cls.DECIMALS[token_symbol]
        }
    
    @classmethod
    def format_amount(cls, amount, token_symbol, precision=2):
        """格式化金额显示"""
        if amount >= 1_000_000:
            return f"{amount/1_000_000:,.{precision}f}M {token_symbol}"
        elif amount >= 1_000:
            return f"{amount/1_000:,.{precision}f}K {token_symbol}"
        else:
            return f"{amount:,.{precision}f} {token_symbol}"


if __name__ == '__main__':
    # 运行测试
    print("TokenParser 模块加载完成")
