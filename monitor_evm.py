import asyncio
import signal
import time
from collections import defaultdict, deque
from web3 import AsyncWeb3
from web3.exceptions import BlockNotFound, TransactionNotFound
from web3.middleware import ExtraDataToPOAMiddleware
from log_utils import get_logger
from config import ActiveConfig
from token_parser import TokenParser  # 导入代币解析器

logger = get_logger(__name__)

class OptimizedMonitor:
    def __init__(self):
        self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(ActiveConfig["rpc_url"]))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.is_running = True
        self.required_confirmations = 3
        
        # 优化策略：减少RPC调用
        self.pending_by_block = defaultdict(list)  # 按区块分组，避免重复查询
        self.confirmed_blocks = set()  # 已确认的区块缓存
        self.last_confirmed_check = 0  # 上次检查确认的时间
        self.confirmation_check_interval = 10  # 每10秒检查一次确认状态
        
        # RPC缓存机制
        self.cached_block_number = None
        self.cache_time = 0
        self.cache_ttl = 1.5  # 缓存1.5秒，避免过于频繁查询
        
        # 交易阈值配置
        self.thresholds = {
            'BNB': 1.0,        # BNB 大额交易阈值
            'USDT': 10000.0,   # USDT 大额交易阈值
            'USDC': 10000.0,   # USDC 大额交易阈值
            'BUSD': 10000.0    # BUSD 大额交易阈值
        }
        
        # 性能统计 - 增加代币统计
        self.stats = {
            'blocks_processed': 0,
            'transactions_found': {
                'BNB': 0,
                'USDT': 0,
                'USDC': 0,
                'BUSD': 0,
                'total': 0
            },
            'rpc_calls': 0,
            'start_time': time.time(),
            'last_stats_log': time.time(),
            'rpc_calls_by_type': {
                'get_block_number': 0,
                'get_block': 0,
                'get_gas_price': 0,
                'other': 0
            },
            'cache_hits': 0,
            'cache_misses': 0,
            'token_transactions_processed': 0,  # 处理的代币交易总数
            'token_contracts_detected': 0       # 检测到的代币合约调用数
        }
        
        # API限制配置
        self.api_limits = {
            'max_rpc_per_second': 4,
            'max_rpc_per_day': 90000,
            'daily_reset_time': None
        }

    def log_rpc_call(self, call_type='other'):
        """记录RPC调用并按类型分类统计"""
        self.stats['rpc_calls'] += 1
        if call_type in self.stats['rpc_calls_by_type']:
            self.stats['rpc_calls_by_type'][call_type] += 1
        else:
            self.stats['rpc_calls_by_type']['other'] += 1
            
        current_time = time.time()
        
        # 检查是否需要重置每日计数
        if self.api_limits['daily_reset_time'] is None:
            self.api_limits['daily_reset_time'] = current_time
        elif current_time - self.api_limits['daily_reset_time'] >= 86400:
            self.api_limits['daily_reset_time'] = current_time
            logger.info("🔄 每日RPC计数已重置")

    async def get_cached_block_number(self):
        """获取缓存的区块号，减少重复RPC调用"""
        current_time = time.time()
        
        if (self.cached_block_number is None or 
            current_time - self.cache_time > self.cache_ttl):
            self.cached_block_number = await self.w3.eth.get_block_number()
            self.cache_time = current_time
            self.log_rpc_call('get_block_number')
            self.stats['cache_misses'] += 1
        else:
            self.stats['cache_hits'] += 1
            
        return self.cached_block_number

    async def check_api_limits(self):
        """检查API调用限制"""
        current_time = time.time()
        runtime = current_time - self.stats['start_time']
        
        avg_rpc_per_second = self.stats['rpc_calls'] / runtime if runtime > 0 else 0
        
        if avg_rpc_per_second > self.api_limits['max_rpc_per_second'] * 0.8:
            delay = 1.0 / self.api_limits['max_rpc_per_second']
            logger.warning(f"⚠️ RPC调用频率过高 ({avg_rpc_per_second:.2f}/s)，添加 {delay:.2f}s 延迟")
            await asyncio.sleep(delay)
        
        if self.stats['rpc_calls'] > self.api_limits['max_rpc_per_day'] * 0.9:
            logger.warning(f"⚠️ 今日RPC调用次数接近限制: {self.stats['rpc_calls']}/{self.api_limits['max_rpc_per_day']}")

    async def handle_transaction(self, tx):
        """处理单个交易 - 包含BNB和代币转账检测（无额外RPC调用）"""
        block_number = tx.get('blockNumber')
        
        # 1. 检测原生 BNB 转账
        wei = tx['value']
        bnb_amount = self.w3.from_wei(wei, 'ether')
        
        if bnb_amount >= self.thresholds['BNB']:
            gas_cost = self.w3.from_wei(tx['gasPrice'] * tx['gas'], 'ether')
            tx_hash = self.w3.to_hex(tx['hash'])
            
            logger.info(
                f"💰 大额BNB: {tx['from']} => {tx['to']} | "
                f"{TokenParser.format_amount(bnb_amount, 'BNB')} | "
                f"Gas: {gas_cost:,.5f} BNB | "
                f"区块: {block_number} | {ActiveConfig['scan_url']}/tx/{tx_hash}"
            )
            
            if block_number:
                self.pending_by_block[block_number].append({
                    'hash': tx_hash,
                    'tx': tx,
                    'value': bnb_amount,
                    'type': 'BNB',
                    'found_at': time.time()
                })
                
            self.stats['transactions_found']['BNB'] += 1
            self.stats['transactions_found']['total'] += 1
        
        # 2. 检测代币转账（如果交易调用了合约）
        if tx.get('to'):
            # 检查是否为支持的代币合约
            token_symbol = TokenParser.is_token_contract(tx['to'])
            if token_symbol:
                self.stats['token_contracts_detected'] += 1
                
                # 解析代币转账
                token_info = TokenParser.parse_erc20_transfer(tx, token_symbol)
                if token_info:
                    self.stats['token_transactions_processed'] += 1
                    
                    # 检查是否为大额转账
                    if token_info['amount'] >= self.thresholds.get(token_symbol, float('inf')):
                        tx_hash = self.w3.to_hex(tx['hash'])
                        
                        # 根据代币类型选择不同的图标
                        icons = {
                            'USDT': '💵',
                            'USDC': '💸', 
                            'BUSD': '💴'
                        }
                        icon = icons.get(token_symbol, '🪙')
                        
                        logger.info(
                            f"{icon} 大额{token_symbol}: {token_info['from']} => {token_info['to']} | "
                            f"{TokenParser.format_amount(token_info['amount'], token_symbol)} | "
                            f"区块: {block_number} | {ActiveConfig['scan_url']}/tx/{tx_hash}"
                        )
                        
                        if block_number:
                            self.pending_by_block[block_number].append({
                                'hash': tx_hash,
                                'tx': tx,
                                'value': token_info['amount'],
                                'type': token_symbol,
                                'token_info': token_info,
                                'found_at': time.time()
                            })
                        
                        self.stats['transactions_found'][token_symbol] += 1
                        self.stats['transactions_found']['total'] += 1

    async def check_block_confirmations(self):
        """批量检查区块确认状态"""
        if not self.pending_by_block:
            return
            
        try:
            current_block = await self.get_cached_block_number()
            await self.check_api_limits()
        except Exception as e:
            logger.error(f"获取当前区块失败: {e}")
            return
        
        blocks_to_remove = []
        newly_confirmed = []
        
        for block_number, tx_list in self.pending_by_block.items():
            confirmations = current_block - block_number + 1
            
            if confirmations >= self.required_confirmations:
                for tx_info in tx_list:
                    newly_confirmed.append({
                        'tx_info': tx_info,
                        'confirmations': confirmations,
                        'block_number': block_number
                    })
                blocks_to_remove.append(block_number)
                
            elif confirmations <= 0:
                logger.warning(f"⚠️ 可能的区块重组，区块 {block_number} 确认数: {confirmations}")
        
        # 记录新确认的交易
        for item in newly_confirmed:
            tx_info = item['tx_info']
            tx = tx_info['tx']
            confirmations = item['confirmations']
            tx_type = tx_info['type']
            
            # 根据交易类型格式化确认信息
            if tx_type == 'BNB':
                logger.info(
                    f"✅ BNB交易确认: {tx['from']} => {tx['to']} | "
                    f"{TokenParser.format_amount(tx_info['value'], 'BNB')} | "
                    f"确认数: {confirmations} | {ActiveConfig['scan_url']}/tx/{tx_info['hash']}"
                )
            else:
                # 代币交易
                token_info = tx_info.get('token_info', {})
                logger.info(
                    f"✅ {tx_type}交易确认: {token_info.get('from', 'N/A')} => {token_info.get('to', 'N/A')} | "
                    f"{TokenParser.format_amount(tx_info['value'], tx_type)} | "
                    f"确认数: {confirmations} | {ActiveConfig['scan_url']}/tx/{tx_info['hash']}"
                )
        
        # 清理已确认的区块
        for block_number in blocks_to_remove:
            del self.pending_by_block[block_number]
            
        if newly_confirmed:
            logger.debug(f"本轮确认了 {len(newly_confirmed)} 个交易")

    async def cleanup_old_transactions(self):
        """清理超时的交易"""
        current_time = time.time()
        blocks_to_remove = []
        timeout_count = 0
        
        for block_number, tx_list in self.pending_by_block.items():
            remaining_txs = []
            for tx_info in tx_list:
                if current_time - tx_info['found_at'] < 300:  # 5分钟
                    remaining_txs.append(tx_info)
                else:
                    timeout_count += 1
                    logger.warning(f"⏰ {tx_info['type']}交易确认超时: {tx_info['hash']}")
            
            if remaining_txs:
                self.pending_by_block[block_number] = remaining_txs
            else:
                blocks_to_remove.append(block_number)
        
        for block_number in blocks_to_remove:
            del self.pending_by_block[block_number]
            
        if timeout_count > 0:
            logger.info(f"清理了 {timeout_count} 个超时交易")

    def log_performance_stats(self):
        """记录详细的性能统计信息"""
        current_time = time.time()
        runtime = current_time - self.stats['start_time']
        
        avg_rpc_per_second = self.stats['rpc_calls'] / runtime if runtime > 0 else 0
        estimated_daily_calls = avg_rpc_per_second * 86400
        
        # 缓存效率
        total_block_requests = self.stats['cache_hits'] + self.stats['cache_misses']
        cache_hit_rate = (self.stats['cache_hits'] / total_block_requests * 100) if total_block_requests > 0 else 0
        
        pending_count = sum(len(txs) for txs in self.pending_by_block.values())
        
        # 按类型统计待确认交易
        pending_by_type = defaultdict(int)
        for tx_list in self.pending_by_block.values():
            for tx_info in tx_list:
                pending_by_type[tx_info['type']] += 1
        
        logger.info(
            f"📊 性能统计 | "
            f"运行: {runtime/3600:.1f}h | "
            f"区块: {self.stats['blocks_processed']} | "
            f"交易: {self.stats['transactions_found']['total']} | "
            f"待确认: {pending_count}"
        )
        
        # 详细的交易类型统计
        tx_breakdown = []
        for tx_type, count in self.stats['transactions_found'].items():
            if tx_type != 'total' and count > 0:
                pending = pending_by_type.get(tx_type, 0)
                tx_breakdown.append(f"{tx_type}: {count}({pending})")
        
        if tx_breakdown:
            logger.info(f"💰 交易分类 | {' | '.join(tx_breakdown)} | (发现数(待确认数))")
        
        # 代币处理统计
        if self.stats['token_contracts_detected'] > 0:
            token_success_rate = (self.stats['token_transactions_processed'] / self.stats['token_contracts_detected']) * 100
            logger.info(
                f"🪙 代币统计 | "
                f"合约调用: {self.stats['token_contracts_detected']} | "
                f"成功解析: {self.stats['token_transactions_processed']} | "
                f"解析率: {token_success_rate:.1f}%"
            )
        
        # RPC调用统计
        rpc_breakdown = " | ".join([
            f"{k}: {v}" for k, v in self.stats['rpc_calls_by_type'].items() if v > 0
        ])
        
        logger.info(
            f"🔗 RPC统计 | "
            f"总计: {self.stats['rpc_calls']} | "
            f"速率: {avg_rpc_per_second:.2f}/s | "
            f"预估日用: {estimated_daily_calls:.0f} | "
            f"缓存命中率: {cache_hit_rate:.1f}%"
        )
        
        logger.info(f"📈 RPC分类 | {rpc_breakdown}")
        
        # API限制状态
        if estimated_daily_calls > self.api_limits['max_rpc_per_day']:
            logger.warning(f"⚠️ 预估日用量超限！当前速度可能耗尽配额")
        elif avg_rpc_per_second > self.api_limits['max_rpc_per_second']:
            logger.warning(f"⚠️ RPC调用频率超限！建议降低到 {self.api_limits['max_rpc_per_second']}/s 以下")
        else:
            logger.info(f"✅ RPC使用率正常，缓存有效降低了调用频率")

    async def monitor_transactions(self):
        last_block = await self.get_cached_block_number()
        logger.info(f"🚀 开始监控 BNB 链交易（包含代币转账），当前区块: {last_block}")
        logger.info(f"📈 监控阈值: BNB≥{self.thresholds['BNB']}, USDT≥{self.thresholds['USDT']:,}, USDC≥{self.thresholds['USDC']:,}, BUSD≥{self.thresholds['BUSD']:,}")
        
        while self.is_running:
            loop_start = time.time()
            
            try:
                current_block = await self.get_cached_block_number()
                await self.check_api_limits()
                
                new_blocks_processed = 0
                for block_number in range(last_block + 1, current_block + 1):
                    if not self.is_running:
                        break
                        
                    try:
                        block = await self.w3.eth.get_block(block_number, full_transactions=True)
                        self.log_rpc_call('get_block')
                        await self.check_api_limits()
                        
                        for tx in block.transactions:
                            if not self.is_running:
                                break
                            await self.handle_transaction(tx)
                        
                        new_blocks_processed += 1
                        self.stats['blocks_processed'] += 1
                        
                    except BlockNotFound:
                        continue
                    except Exception as e:
                        logger.error(f"处理区块 {block_number} 失败: {e}")
                        continue
                
                current_time = time.time()
                if current_time - self.last_confirmed_check >= self.confirmation_check_interval:
                    await self.check_block_confirmations()
                    self.last_confirmed_check = current_time
                
                if current_time % 60 < 1:
                    await self.cleanup_old_transactions()
                
                if current_time - self.stats['last_stats_log'] >= 300:
                    self.log_performance_stats()
                    self.stats['last_stats_log'] = current_time
                
                if current_block > last_block:
                    if new_blocks_processed > 0:
                        pending_count = sum(len(txs) for txs in self.pending_by_block.values())
                        runtime = current_time - self.stats['start_time']
                        avg_rpc_per_second = self.stats['rpc_calls'] / runtime if runtime > 0 else 0
                        
                        logger.info(
                            f"📈 处理 {new_blocks_processed} 新区块 | "
                            f"当前: {current_block} | "
                            f"待确认: {pending_count} | "
                            f"RPC: {self.stats['rpc_calls']} ({avg_rpc_per_second:.2f}/s) | "
                            f"缓存: {self.stats['cache_hits']}/{self.stats['cache_hits'] + self.stats['cache_misses']} | "
                            f"发现: {self.stats['transactions_found']['total']}"
                        )
                    
                    last_block = current_block
                
                # 动态调整等待时间
                loop_time = time.time() - loop_start
                if loop_time > 2:
                    logger.warning(f"⚠️ 处理耗时 {loop_time:.2f}s，可能跟不上出块速度")
                    await asyncio.sleep(0.1)
                else:
                    await asyncio.sleep(max(0.1, 1 - loop_time))
                
            except Exception as e:
                logger.error(f"监控循环发生错误: {e}", exc_info=True)
                await asyncio.sleep(5)

        logger.info("监控已停止")

    def stop(self):
        self.is_running = False
        logger.info("正在停止监控...")

    def get_stats(self):
        """获取详细的性能统计"""
        runtime = time.time() - self.stats['start_time']
        avg_rpc_per_second = self.stats['rpc_calls'] / runtime if runtime > 0 else 0
        
        # 计算缓存效率
        total_requests = self.stats['cache_hits'] + self.stats['cache_misses']
        cache_hit_rate = (self.stats['cache_hits'] / total_requests) if total_requests > 0 else 0
        
        return {
            'runtime_seconds': runtime,
            'runtime_hours': runtime / 3600,
            'blocks_processed': self.stats['blocks_processed'],
            'transactions_found': self.stats['transactions_found'].copy(),
            'rpc_calls_total': self.stats['rpc_calls'],
            'rpc_calls_per_second': avg_rpc_per_second,
            'rpc_calls_per_minute': avg_rpc_per_second * 60,
            'estimated_daily_rpc_calls': avg_rpc_per_second * 86400,
            'rpc_calls_by_type': self.stats['rpc_calls_by_type'].copy(),
            'cache_hit_rate': cache_hit_rate * 100,
            'cache_hits': self.stats['cache_hits'],
            'cache_misses': self.stats['cache_misses'],
            'pending_transactions': sum(len(txs) for txs in self.pending_by_block.values()),
            'api_limit_usage_percent': (self.stats['rpc_calls'] / self.api_limits['max_rpc_per_day']) * 100,
            'within_rate_limit': avg_rpc_per_second <= self.api_limits['max_rpc_per_second'],
            'token_stats': {
                'contracts_detected': self.stats['token_contracts_detected'],
                'transactions_processed': self.stats['token_transactions_processed'],
                'success_rate': (self.stats['token_transactions_processed'] / self.stats['token_contracts_detected'] * 100) if self.stats['token_contracts_detected'] > 0 else 0
            }
        }

    def update_thresholds(self, **thresholds):
        """动态更新交易阈值"""
        for token, threshold in thresholds.items():
            if token in self.thresholds:
                old_threshold = self.thresholds[token]
                self.thresholds[token] = threshold
                logger.info(f"🔧 更新{token}阈值: {old_threshold} => {threshold}")
            else:
                logger.warning(f"⚠️ 未知的代币类型: {token}")
        
        logger.info(f"📈 当前阈值: {self.thresholds}")


async def main():
    monitor = OptimizedMonitor()

    def signal_handler(_, _2):
        logger.info("接收到停止信号，正在优雅退出...")
        stats = monitor.get_stats()
        
        logger.info("=" * 80)
        logger.info("📈 最终运行统计报告")
        logger.info(f"🕒 运行时长: {stats['runtime_hours']:.2f} 小时")
        logger.info(f"📦 处理区块: {stats['blocks_processed']} 个")
        
        # 详细的交易统计
        tx_found = stats['transactions_found']
        logger.info(f"💰 发现交易: {tx_found['total']} 笔")
        for tx_type, count in tx_found.items():
            if tx_type != 'total' and count > 0:
                logger.info(f"   {tx_type}: {count} 笔")
        
        # 代币处理统计
        token_stats = stats['token_stats']
        if token_stats['contracts_detected'] > 0:
            logger.info(f"🪙 代币统计:")
            logger.info(f"   合约调用检测: {token_stats['contracts_detected']} 次")
            logger.info(f"   成功解析转账: {token_stats['transactions_processed']} 次")
            logger.info(f"   解析成功率: {token_stats['success_rate']:.1f}%")
        
        # RPC使用统计
        logger.info(f"🔗 RPC调用: {stats['rpc_calls_total']} 次")
        logger.info(f"⚡ 平均速度: {stats['rpc_calls_per_second']:.2f} 次/秒")
        logger.info(f"📊 预估日用量: {stats['estimated_daily_rpc_calls']:.0f} 次")
        logger.info(f"📈 配额使用率: {stats['api_limit_usage_percent']:.1f}%")
        logger.info(f"🎯 缓存命中率: {stats['cache_hit_rate']:.1f}% ({stats['cache_hits']}/{stats['cache_hits']+stats['cache_misses']})")
        
        logger.info("🔍 RPC调用分类:")
        for call_type, count in stats['rpc_calls_by_type'].items():
            if count > 0:
                percentage = (count / stats['rpc_calls_total']) * 100
                logger.info(f"   {call_type}: {count} 次 ({percentage:.1f}%)")
        
        logger.info(f"✅ 速率合规: {'是' if stats['within_rate_limit'] else '否'}")
        logger.info(f"⏳ 待确认交易: {stats['pending_transactions']} 笔")
        logger.info("=" * 80)
        
        monitor.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 检查网络连接
    try:
        latest_block = await monitor.get_cached_block_number()
        gas_price = await monitor.w3.eth.gas_price
        monitor.log_rpc_call('get_gas_price')
        gas_price_gwei = monitor.w3.from_wei(gas_price, 'gwei')
        logger.info(f"🌐 BNB 链连接成功 - 区块: {latest_block}, Gas: {gas_price_gwei:.2f} Gwei")
        
        # 显示支持的代币信息
        logger.info("🪙 支持的代币合约:")
        for token, contract in TokenParser.CONTRACTS.items():
            if contract:
                logger.info(f"   {token}: {contract}")
        
    except Exception as e:
        logger.error(f"网络连接失败: {e}")
        return

    # 开始监控
    await monitor.monitor_transactions()


if __name__ == '__main__':
    asyncio.run(main())