import requests
import time
import json
import logging
from typing import List, Dict, Optional
from config.base_config import LoggingConfig, AddressLoadConfig

# 配置日志
logging.basicConfig(level=logging.INFO, format=LoggingConfig.get('format', '%(asctime)s - %(levelname)s - %(message)s'))
logger = logging.getLogger(__name__)

class AddressLoader:
    """
    一个工业级的地址加载器，用于从HTTP Dump接口获取历史钱包地址数据。

    支持分页和按地址类型筛选，并内置重试机制。
    """

    def __init__(self, 
                 base_url: str, 
                 default_page_size: int = 1000, 
                 max_retries: int = 5, 
                 retry_delay_seconds: int = 5,
                 timeout_seconds: int = 30):

        if not base_url:
            raise ValueError("base_url 不能为空")
        if not base_url.endswith("/dump"): # 强制要求以 /dump 结尾，提高url校验的鲁棒性
            logger.warning(f"base_url '{base_url}' does not end with '/dump'. Appending it.")
            base_url = f"{base_url.rstrip('/')}/dump" # rstrip('/') 防止重复斜杠

        self.base_url = base_url
        self.default_page_size = default_page_size
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.timeout_seconds = timeout_seconds
        logger.info(f"AddressLoader initialized with base_url: {self.base_url}")

    def _make_request(self, params: Dict) -> Optional[Dict]:
        """
        执行HTTP GET请求，并处理重试逻辑。

        Args:
            params (Dict): 请求参数（page, pageSize, address_type）。

        Returns:
            Optional[Dict]: 成功时返回JSON响应数据，失败时返回None。
        """
        attempt = 0
        while attempt < self.max_retries:
            try:
                logger.info(f"Fetching data from {self.base_url} with params: {params} (Attempt {attempt + 1}/{self.max_retries})")
                response = requests.get(self.base_url, params=params, timeout=self.timeout_seconds)
                response.raise_for_status()  # 如果响应状态码不是2xx，则抛出HTTPError

                data = response.json()
                if data.get("success"):
                    return data
                else:
                    error_msg = data.get("error", "Unknown error from API")
                    logger.error(f"API returned non-success response: {error_msg} for params: {params}")
                    # 对于业务逻辑错误，不重试，直接返回None或抛出特定异常
                    return None
            except requests.exceptions.Timeout:
                logger.warning(f"Request timed out after {self.timeout_seconds}s for params: {params}")
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Connection error: {e} for params: {params}")
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error occurred: {e} for params: {params}. Status Code: {response.status_code}")
                if 400 <= response.status_code < 500 and response.status_code != 429: # 客户端错误，通常不重试，除非是限流
                    logger.error(f"Non-retriable client error for params: {params}. Exiting retry loop.")
                    return None
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON response from {self.base_url} for params: {params}")
            except Exception as e:
                logger.error(f"An unexpected error occurred during request: {e} for params: {params}")

            attempt += 1
            if attempt < self.max_retries:
                logger.info(f"Retrying in {self.retry_delay_seconds} seconds...")
                time.sleep(self.retry_delay_seconds)
        
        logger.error(f"Failed to fetch data after {self.max_retries} attempts for params: {params}")
        return None

    def load_all_addresses(self, 
                           address_type: Optional[str] = None, 
                           page_size: Optional[int] = None) -> List[Dict]:
        """
        从HTTP Dump接口加载所有匹配的钱包地址。

        此方法将自动处理分页，循环获取所有数据。

        Args:
            address_type (Optional[str]): 要筛选的地址类型，例如 "EVM", "TRON"。
                                          如果为None，则获取所有类型的地址。
            page_size (Optional[int]): 本次加载操作使用的页大小。如果为None，则使用实例的默认页大小。

        Returns:
            List[Dict]: 包含所有获取到的钱包地址字典的列表。
        """
        all_addresses: List[Dict] = []
        current_page = 1
        total_pages = 1  # 初始值，会在第一次请求后更新
        effective_page_size = page_size if page_size is not None else self.default_page_size

        logger.info(f"Starting to load addresses. Type filter: {address_type if address_type else 'None'}, Page size: {effective_page_size}")

        while current_page <= total_pages:
            params = {
                "page": current_page,
                "pageSize": effective_page_size
            }
            if address_type:
                params["address_type"] = address_type

            response_data = self._make_request(params)

            if response_data is None:
                logger.error(f"Failed to get data for page {current_page}. Aborting load process.")
                break # 遇到不可恢复错误，停止加载

            dump_data = response_data.get("data", {})
            addresses_list = dump_data
            pagination_info = response_data.get("pagination", {})
            total_count = pagination_info.get("total", 0)

            all_addresses.extend(addresses_list)

            # 更新总页数
            total_pages = (total_count + effective_page_size - 1) // effective_page_size

            logger.info(f"Fetched page {current_page}/{total_pages}. Total addresses fetched so far: {len(all_addresses)} / {total_count}")

            current_page += 1
            
            # 避免请求过于频繁，对服务器造成压力
            if current_page <= total_pages: # 如果还有下一页，才延迟
                time.sleep(0.05) # 短暂延迟，可根据实际情况调整

        logger.info(f"Finished loading addresses. Total addresses collected: {len(all_addresses)}")
        return all_addresses


def load_evm_wallet_addresses() -> List[str]:
    loader = AddressLoader(
        base_url=AddressLoadConfig.get('base_url', 'http://localhost:8081/api/v1/addresses/dump'),
        default_page_size=AddressLoadConfig.get('default_page_size', 1000),
        max_retries=AddressLoadConfig.get('max_retries', 5),
        retry_delay_seconds=AddressLoadConfig.get('retry_delay_seconds', 5),
        timeout_seconds=AddressLoadConfig.get('timeout_seconds', 30)
    )

    address_list = loader.load_all_addresses(address_type="evm")
    return address_list



if __name__ == "__main__":
    address_list = load_evm_wallet_addresses()
    print(f"Total addresses loaded: {len(address_list)}")
    for address in address_list[:5]:  # 打印前5个地址
        print(address)