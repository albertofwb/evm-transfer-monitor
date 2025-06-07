"""
网络连接验证模块

负责验证网络连接和显示连接信息
"""

from typing import Dict, Any

from managers.rpc_manager import RPCManager
from utils.token_parser import TokenParser
from utils.log_utils import get_logger

logger = get_logger(__name__)


class NetworkValidator:
    """网络连接验证器"""
    
    def __init__(self, rpc_manager: RPCManager, token_parser: TokenParser):
        """
        初始化网络验证器
        
        Args:
            rpc_manager: RPC管理器
            token_parser: 代币解析器
        """
        self.rpc_manager = rpc_manager
        self.token_parser = token_parser
    
    async def check_network_connection(self) -> Dict[str, Any]:
        """
        检查网络连接
        
        Returns:
            连接信息字典
            
        Raises:
            ConnectionError: 连接失败时抛出
        """
        logger.info("🌐 正在检查网络连接...")
        
        connection_info = await self.rpc_manager.test_connection()
        
        if connection_info['success']:
            logger.info(
                f"🌐 {connection_info['network']} 连接成功 - "
                f"区块: {connection_info['latest_block']}, "
                f"Gas: {connection_info['gas_price_gwei']:.2f} Gwei"
            )
            
            # 显示支持的代币信息
            self._log_supported_tokens()
            return connection_info
        else:
            error_msg = f"网络连接失败: {connection_info['error']}"
            logger.error(error_msg)
            raise ConnectionError(f"无法连接到RPC: {connection_info['error']}")
    
    def _log_supported_tokens(self) -> None:
        """记录支持的代币信息"""
        logger.info("🪙 支持的代币合约:")
        for token, contract in self.token_parser.contracts.items():
            if contract:
                logger.info(f"   {token}: {contract}")
