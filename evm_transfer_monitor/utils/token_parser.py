"""
改进的代币转账解析辅助方法
用于解析 ERC-20 代币的转账交易，支持多链配置，增强了对不规范数据的处理能力
"""

from utils.log_utils import get_logger
from config.base_config import ActiveConfig, ConfigMap

logger = get_logger(__name__)

class TokenParser:
    """代币转账解析器 - 多链支持版本"""
    
    # ERC-20 标准方法签名
    TRANSFER_SIGNATURE = '0xa9059cbb'  # transfer(address,uint256)
    
    def __init__(self, chain_name=None):
        """
        初始化解析器
        
        Args:
            chain_name: 指定链名称，如果不指定则使用活跃链配置
        """
        if chain_name:
            self.config = ConfigMap.get(chain_name, {})
            self.chain_name = chain_name
        else:
            self.config = ActiveConfig
            # 从 ConfigMap 中找到当前配置对应的链名称
            self.chain_name = self._get_active_chain_name()
        
        # 从配置中构建代币信息
        self._build_token_info()
    
    def _get_active_chain_name(self):
        """获取当前活跃链的名称"""
        for chain_name, config in ConfigMap.items():
            if config == self.config:
                return chain_name
        return "unknown"
    
    def _build_token_info(self):
        """从配置文件构建代币信息"""
        self.contracts = {}
        self.decimals = {}
        
        # 添加原生代币
        if 'token_name' in self.config:
            native_token = self.config['token_name']
            self.contracts[native_token] = None  # 原生代币没有合约地址
            self.decimals[native_token] = 18  # 大多数 EVM 链的原生代币都是18位小数
        
        # 添加 USDT
        if 'usdt_contract' in self.config:
            self.contracts['USDT'] = self.config['usdt_contract']
            self.decimals['USDT'] = 18  # 现在大多数链上的USDT都是18位小数
        
        # 添加 USDC
        if 'usdc_contract' in self.config:
            self.contracts['USDC'] = self.config['usdc_contract']
            self.decimals['USDC'] = 18  # 现在大多数链上的USDC都是18位小数
        
        # 添加 BUSD (如果配置中有)
        if 'busd_contract' in self.config:
            self.contracts['BUSD'] = self.config['busd_contract']
            self.decimals['BUSD'] = 18
        
        # 添加其他自定义代币 (如果配置中有)
        if 'custom_tokens' in self.config:
            for token_info in self.config['custom_tokens']:
                symbol = token_info.get('symbol')
                contract = token_info.get('contract')
                decimals = token_info.get('decimals', 18)
                
                if symbol and contract:
                    self.contracts[symbol] = contract
                    self.decimals[symbol] = decimals
    
    def parse_erc20_transfer(self, tx, token_symbol='USDT'):
        """
        解析 ERC-20 代币转账交易 - 改进版，能处理不规范的input数据
        
        Args:
            tx: 交易对象
            token_symbol: 代币符号，默认 USDT
            
        Returns:
            dict: 包含转账信息的字典，解析失败返回 None
        """
        if token_symbol not in self.contracts:
            logger.debug(f"当前链 {self.chain_name} 不支持的代币类型: {token_symbol}")
            return None
            
        contract_address = self.contracts[token_symbol]
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
        if hex_data[:8].lower() != self.TRANSFER_SIGNATURE[2:].lower():
            logger.debug(f"方法签名不匹配: {hex_data[:8]} != {self.TRANSFER_SIGNATURE[2:]}")
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
            decimals = self.decimals.get(token_symbol, 18)
            amount = amount_wei / (10 ** decimals)
            
            # 验证地址格式
            if not self._is_valid_address(to_address):
                logger.debug(f"解析出的地址格式不正确: {to_address}")
                return None
            
            return {
                'from': tx['from'],
                'to': to_address.lower(),
                'amount': amount,
                'token': token_symbol,
                'contract': contract_address.lower(),
                'raw_amount_wei': amount_wei,
                'chain': self.chain_name
            }
            
        except (ValueError, IndexError) as e:
            logger.debug(f"解析{token_symbol}转账失败: {e}, input_data类型: {type(tx.get('input'))}, 长度: {len(str(tx.get('input', '')))}")
            return None
        except Exception as e:
            logger.error(f"解析{token_symbol}转账发生未预期错误: {e}, input数据: {tx.get('input', 'N/A')[:100]}...")
            return None
    
    def _is_valid_address(self, address):
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
    
    def parse_usdt_transfer(self, tx):
        """解析 USDT 转账（快捷方法）"""
        return self.parse_erc20_transfer(tx, 'USDT')
    
    def parse_usdc_transfer(self, tx):
        """解析 USDC 转账（快捷方法）"""
        return self.parse_erc20_transfer(tx, 'USDC')
    
    def parse_busd_transfer(self, tx):
        """解析 BUSD 转账（快捷方法）"""
        return self.parse_erc20_transfer(tx, 'BUSD')
    
    def is_token_contract(self, address):
        """检查地址是否为支持的代币合约"""
        if not address:
            return False
        address = address.lower()
        for token, contract in self.contracts.items():
            if contract and contract.lower() == address:
                return token
        return None
    
    def get_token_info(self, token_symbol):
        """获取代币信息"""
        if token_symbol not in self.contracts:
            return None
        return {
            'symbol': token_symbol,
            'contract': self.contracts[token_symbol],
            'decimals': self.decimals[token_symbol],
            'chain': self.chain_name
        }
    
    def get_supported_tokens(self):
        """获取当前链支持的所有代币列表"""
        return list(self.contracts.keys())
    
    def format_amount(self, amount, token_symbol, precision=2):
        """格式化金额显示"""
        if amount >= 1_000_000:
            return f"{amount/1_000_000:,.{precision}f}M {token_symbol}"
        elif amount >= 1_000:
            return f"{amount/1_000:,.{precision}f}K {token_symbol}"
        else:
            if token_symbol in self.decimals:
                precision = self.decimals[token_symbol]
            else:
                precision = 2
            return f"{amount:,.{precision}f} {token_symbol}"


# 全局默认解析器实例（使用当前活跃链配置）
_default_parser = TokenParser()

# 兼容性方法 - 保持向后兼容
def parse_erc20_transfer(tx, token_symbol='USDT'):
    """全局函数 - 向后兼容"""
    return _default_parser.parse_erc20_transfer(tx, token_symbol)

def parse_usdt_transfer(tx):
    """全局函数 - 向后兼容"""
    return _default_parser.parse_usdt_transfer(tx)

def parse_usdc_transfer(tx):
    """全局函数 - 向后兼容"""
    return _default_parser.parse_usdc_transfer(tx)

def parse_busd_transfer(tx):
    """全局函数 - 向后兼容"""
    return _default_parser.parse_busd_transfer(tx)

def is_token_contract(address):
    """全局函数 - 向后兼容"""
    return _default_parser.is_token_contract(address)

def get_token_info(token_symbol):
    """全局函数 - 向后兼容"""
    return _default_parser.get_token_info(token_symbol)

def format_amount(amount, token_symbol, precision=2):
    """全局函数 - 向后兼容"""
    return _default_parser.format_amount(amount, token_symbol, precision)


if __name__ == '__main__':
    # 运行测试
    print("TokenParser 模块加载完成")
    print(f"当前活跃链: {_default_parser.chain_name}")
    print(f"支持的代币: {_default_parser.get_supported_tokens()}")
    
    # 测试多链支持
    print("\n=== 测试多链支持 ===")
    for chain_name in ConfigMap.keys():
        parser = TokenParser(chain_name)
        print(f"{chain_name} 链支持的代币: {parser.get_supported_tokens()}")
