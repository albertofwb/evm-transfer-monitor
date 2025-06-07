"""
统计报告器

负责性能统计和日志输出，提供监控运行状态的详细报告
"""

import time
from typing import Dict, Any

from config.monitor_config import MonitorConfig
from managers.rpc_manager import RPCManager
from processors.transaction_processor import TransactionProcessor
from managers.confirmation_manager import ConfirmationManager
from models.data_types import MonitorStatus
from utils.log_utils import get_logger

logger = get_logger(__name__)


class StatisticsReporter:
    """统计报告器 - 负责性能统计和日志输出"""
    
    def __init__(self, config: MonitorConfig):
        self.config = config
        self.blocks_processed: int = 0
        self.start_time: float = time.time()
        self.last_stats_log: float = time.time()
        self.peak_rpc_rate: float = 0.0
        self.peak_pending_count: int = 0
        
        # 区块处理时间统计
        self.processing_times: list = []  # 存储最近的处理时间
        self.max_processing_time: float = 0.0
        self.min_processing_time: float = float('inf')
        self.total_processing_time: float = 0.0
    
    def increment_blocks_processed(self) -> None:
        """增加已处理区块数"""
        self.blocks_processed += 1
    
    def should_log_stats(self) -> bool:
        """检查是否应该输出统计日志"""
        current_time = time.time()
        return current_time - self.last_stats_log >= self.config.stats_log_interval
    
    def log_performance_stats(self, rpc_manager: RPCManager, 
                            tx_processor: TransactionProcessor, 
                            confirmation_manager: ConfirmationManager) -> None:
        """输出详细的性能统计"""
        current_time = time.time()
        runtime = current_time - self.start_time
        
        rpc_stats = rpc_manager.get_performance_stats()
        tx_stats = tx_processor.get_stats()
        pending_count = confirmation_manager.get_pending_count()
        pending_by_type = confirmation_manager.get_pending_by_type()
        
        # 更新峰值统计
        self.peak_rpc_rate = max(self.peak_rpc_rate, rpc_stats.avg_rpc_per_second)
        self.peak_pending_count = max(self.peak_pending_count, pending_count)
        
        # 基本运行统计
        logger.info(
            f"📊 性能统计 | "
            f"运行: {runtime/3600:.1f}h | "
            f"区块: {self.blocks_processed} | "
            f"交易: {tx_stats.transactions_found.get('total', 0)} | "
            f"待确认: {pending_count}"
        )
        
        # 交易类型统计
        self._log_transaction_breakdown(tx_stats.transactions_found, pending_by_type)
        
        # 代币处理统计
        if tx_stats.token_contracts_detected > 0:
            logger.info(
                f"🪙 代币统计 | "
                f"合约调用: {tx_stats.token_contracts_detected} | "
                f"成功解析: {tx_stats.token_transactions_processed} | "
                f"解析率: {tx_stats.token_success_rate:.1f}%"
            )
        
        # RPC统计
        self._log_rpc_stats(rpc_stats)
        
        # 确认统计
        self._log_confirmation_stats(confirmation_manager)
        
        self.last_stats_log = current_time
    
    def _log_transaction_breakdown(self, found: Dict[str, int], pending: Dict[str, int]) -> None:
        """记录交易分类统计"""
        tx_breakdown = []
        for tx_type, count in found.items():
            if tx_type != 'total' and count > 0:
                pending_count = pending.get(tx_type, 0)
                tx_breakdown.append(f"{tx_type}: {count}({pending_count})")
        
        if tx_breakdown:
            logger.info(f"💰 交易分类 | {' | '.join(tx_breakdown)} | (发现数(待确认数))")
    
    def _log_rpc_stats(self, rpc_stats) -> None:
        """记录RPC统计信息"""
        rpc_breakdown = " | ".join([
            f"{k}: {v}" for k, v in rpc_stats.rpc_calls_by_type.items() if v > 0
        ])
        
        logger.info(
            f"🔗 RPC统计 | "
            f"总计: {rpc_stats.rpc_calls} | "
            f"速率: {rpc_stats.avg_rpc_per_second:.2f}/s | "
            f"预估日用: {rpc_stats.estimated_daily_calls:.0f} | "
            f"缓存命中率: {rpc_stats.cache_hit_rate:.1f}%"
        )
        
        logger.info(f"📈 RPC分类 | {rpc_breakdown}")
        
        # API限制状态
        self._log_api_limit_status(rpc_stats)
    
    def _log_api_limit_status(self, rpc_stats) -> None:
        """记录API限制状态"""
        if rpc_stats.estimated_daily_calls > self.config.max_rpc_per_day:
            logger.warning("⚠️ 预估日用量超限！当前速度可能耗尽配额")
        elif not rpc_stats.within_rate_limit:
            logger.warning(f"⚠️ RPC调用频率超限！建议降低到 {self.config.max_rpc_per_second}/s 以下")
        else:
            logger.info("✅ RPC使用率正常，缓存有效降低了调用频率")
    
    def _log_confirmation_stats(self, confirmation_manager: ConfirmationManager) -> None:
        """记录确认统计信息"""
        conf_stats = confirmation_manager.get_stats()
        if conf_stats['pending_count'] > 0:
            oldest_age = conf_stats['oldest_pending_age']
            logger.info(
                f"⏳ 确认统计 | "
                f"总计确认: {conf_stats['confirmed_transactions']} | "
                f"超时清理: {conf_stats['timeout_transactions']} | "
                f"最老待确认: {oldest_age:.0f}s"
            )
    
    def log_processing_progress(self, new_blocks: int, current_block: int, 
                             rpc_manager: RPCManager, tx_processor: TransactionProcessor, 
                             confirmation_manager: ConfirmationManager, 
                             processing_time: float = None) -> None:
        """记录处理进度
        
        Args:
            new_blocks: 新处理的区块数量
            current_block: 当前区块号
            rpc_manager: RPC管理器
            tx_processor: 交易处理器
            confirmation_manager: 确认管理器
            processing_time: 处理这批区块花费的时间（秒），可选参数
        """
        pending_count = confirmation_manager.get_pending_count()
        rpc_stats = rpc_manager.get_performance_stats()
        tx_stats = tx_processor.get_stats()
        
        # 构建基础日志信息
        log_parts = [
            f"📈 处理 {new_blocks} 新区块",
            f"当前: {current_block}",
            f"待确认: {pending_count}",
            f"RPC: {rpc_stats.rpc_calls} ({rpc_stats.avg_rpc_per_second:.2f}/s)",
            f"缓存: {rpc_stats.cache_hits}/{rpc_stats.cache_hits + rpc_stats.cache_misses}",
            f"发现: {tx_stats.transactions_found.get('total', 0)} 笔交易"
        ]
        
        # 如果提供了处理时间，添加时间统计
        if processing_time is not None:
            # 更新处理时间统计
            self._update_processing_time_stats(processing_time)
            
            # 计算每个区块的平均处理时间
            avg_time_per_block = processing_time / max(new_blocks, 1)
            # 计算区块处理速率
            blocks_per_second = new_blocks / max(processing_time, 0.001)
            
            # 获取最近的平均处理旷间（最近10次）
            recent_avg = self._get_recent_average_processing_time()
            
            log_parts.insert(1, f"耗时: {processing_time:.2f}s")
            log_parts.insert(2, f"速率: {blocks_per_second:.1f} 区块/s")
            log_parts.insert(3, f"均时: {avg_time_per_block:.3f}s/区块")
            
            # 如果有足够的历史数据，显示近期平均
            if recent_avg is not None:
                log_parts.append(f"近期平均: {recent_avg:.3f}s/区块")
        
        logger.info(" | ".join(log_parts))
    
    def _update_processing_time_stats(self, processing_time: float) -> None:
        """更新处理时间统计数据"""
        # 更新最大、最小处理时间
        self.max_processing_time = max(self.max_processing_time, processing_time)
        if self.min_processing_time == float('inf'):
            self.min_processing_time = processing_time
        else:
            self.min_processing_time = min(self.min_processing_time, processing_time)
        
        # 累计总处理时间
        self.total_processing_time += processing_time
        
        # 保存最近50次的处理时间记录
        self.processing_times.append(processing_time)
        if len(self.processing_times) > 50:
            self.processing_times.pop(0)
    
    def _get_recent_average_processing_time(self) -> float:
        """获取最近的平均处理时间（最近10次）"""
        if len(self.processing_times) < 3:  # 至少需要有3次记录
            return None
        
        recent_times = self.processing_times[-10:]  # 取最近10次
        return sum(recent_times) / len(recent_times)
    
    def get_processing_time_stats(self) -> dict:
        """获取处理时间统计数据"""
        if not self.processing_times:
            return {
                'count': 0,
                'total_time': 0.0,
                'avg_time': 0.0,
                'min_time': 0.0,
                'max_time': 0.0,
                'recent_avg': 0.0
            }
        
        return {
            'count': len(self.processing_times),
            'total_time': self.total_processing_time,
            'avg_time': self.total_processing_time / len(self.processing_times),
            'min_time': self.min_processing_time if self.min_processing_time != float('inf') else 0.0,
            'max_time': self.max_processing_time,
            'recent_avg': self._get_recent_average_processing_time() or 0.0
        }
    
    def log_final_stats(self, rpc_manager: RPCManager, 
                       tx_processor: TransactionProcessor, 
                       confirmation_manager: ConfirmationManager) -> None:
        """输出最终统计报告"""
        runtime = time.time() - self.start_time
        rpc_stats = rpc_manager.get_performance_stats()
        tx_stats = tx_processor.get_stats()
        conf_stats = confirmation_manager.get_stats()
        
        logger.info("=" * 80)
        logger.info("📈 最终运行统计报告")
        logger.info(f"🕒 运行时长: {runtime/3600:.2f} 小时")
        logger.info(f"📦 处理区块: {self.blocks_processed} 个")
        
        # 交易统计
        self._log_final_transaction_stats(tx_stats.transactions_found)
        
        # 代币处理统计
        self._log_final_token_stats(tx_stats)
        
        # RPC统计
        self._log_final_rpc_stats(rpc_stats)
        
        # 确认统计
        self._log_final_confirmation_stats(conf_stats)
        
        # 峰值统计
        logger.info(f"🎯 峰值统计:")
        logger.info(f"   最高RPC速率: {self.peak_rpc_rate:.2f} 次/秒")
        logger.info(f"   最大待确认数: {self.peak_pending_count} 笔")
        
        # 区块处理时间统计
        self._log_final_processing_time_stats()
        
        logger.info("=" * 80)
    
    def _log_final_transaction_stats(self, found: Dict[str, int]) -> None:
        """记录最终交易统计"""
        logger.info(f"💰 发现交易: {found.get('total', 0)} 笔")
        for tx_type, count in found.items():
            if tx_type != 'total' and count > 0:
                logger.info(f"   {tx_type}: {count} 笔")
    
    def _log_final_token_stats(self, tx_stats) -> None:
        """记录最终代币统计"""
        if tx_stats.token_contracts_detected > 0:
            logger.info("🪙 代币统计:")
            logger.info(f"   合约调用检测: {tx_stats.token_contracts_detected} 次")
            logger.info(f"   成功解析转账: {tx_stats.token_transactions_processed} 次")
            logger.info(f"   解析成功率: {tx_stats.token_success_rate:.1f}%")
    
    def _log_final_rpc_stats(self, rpc_stats) -> None:
        """记录最终RPC统计"""
        logger.info(f"🔗 RPC调用: {rpc_stats.rpc_calls} 次")
        logger.info(f"⚡ 平均速度: {rpc_stats.avg_rpc_per_second:.2f} 次/秒")
        logger.info(f"📊 预估日用量: {rpc_stats.estimated_daily_calls:.0f} 次")
        logger.info(f"📈 配额使用率: {rpc_stats.api_usage_percent:.1f}%")
        logger.info(f"🎯 缓存命中率: {rpc_stats.cache_hit_rate:.1f}%")
        
        logger.info("🔍 RPC调用分类:")
        for call_type, count in rpc_stats.rpc_calls_by_type.items():
            if count > 0:
                percentage = (count / rpc_stats.rpc_calls) * 100
                logger.info(f"   {call_type}: {count} 次 ({percentage:.1f}%)")
        
        logger.info(f"✅ 速率合规: {'是' if rpc_stats.within_rate_limit else '否'}")
    
    def _log_final_confirmation_stats(self, conf_stats: Dict[str, Any]) -> None:
        """记录最终确认统计"""
        logger.info(f"⏳ 确认统计:")
        logger.info(f"   总计确认: {conf_stats['confirmed_transactions']} 笔")
        logger.info(f"   超时清理: {conf_stats['timeout_transactions']} 笔")
        logger.info(f"   剩余待确认: {conf_stats['pending_count']} 笔")
    
    def _log_final_processing_time_stats(self) -> None:
        """记录最终处理时间统计"""
        stats = self.get_processing_time_stats()
        
        if stats['count'] > 0:
            logger.info(f"⏱️ 处理时间统计:")
            logger.info(f"   处理批次: {stats['count']} 次")
            logger.info(f"   总耗时: {stats['total_time']:.2f} 秒")
            logger.info(f"   平均耗时: {stats['avg_time']:.3f} 秒/批")
            logger.info(f"   最快处理: {stats['min_time']:.3f} 秒")
            logger.info(f"   最慢处理: {stats['max_time']:.3f} 秒")
            if stats['recent_avg'] > 0:
                logger.info(f"   近期平均: {stats['recent_avg']:.3f} 秒/批")
        else:
            logger.info("⏱️ 无处理时间数据")
    
    def get_monitor_status(self, current_block: int, is_running: bool) -> MonitorStatus:
        """获取当前监控状态"""
        current_time = time.time()
        status = MonitorStatus(
            is_running=is_running,
            blocks_processed=self.blocks_processed,
            start_time=self.start_time,
            current_block=current_block,
            last_activity=current_time
        )
        status.update_runtime(current_time)
        return status
    
    def get_comprehensive_report(self, rpc_manager: RPCManager, 
                               tx_processor: TransactionProcessor, 
                               confirmation_manager: ConfirmationManager) -> Dict[str, Any]:
        """获取综合报告"""
        runtime = time.time() - self.start_time
        
        return {
            'runtime': {
                'seconds': runtime,
                'hours': runtime / 3600,
                'formatted': f"{runtime/3600:.2f}h"
            },
            'blocks_processed': self.blocks_processed,
            'transactions': tx_processor.get_transaction_summary(),
            'rpc_performance': rpc_manager.get_performance_stats().__dict__,
            'confirmations': confirmation_manager.get_stats(),
            'peak_metrics': {
                'max_rpc_rate': self.peak_rpc_rate,
                'max_pending_count': self.peak_pending_count,
                'processing_time_stats': self.get_processing_time_stats()
            },
            'configuration_summary': {
                'thresholds': self.config.thresholds.copy(),
                'confirmations_required': self.config.required_confirmations,
                'rate_limits': {
                    'rpc_per_second': self.config.max_rpc_per_second,
                    'rpc_per_day': self.config.max_rpc_per_day
                }
            }
        }
    
    def reset_stats(self) -> None:
        """重置统计数据"""
        self.blocks_processed = 0
        self.start_time = time.time()
        self.last_stats_log = time.time()
        self.peak_rpc_rate = 0.0
        self.peak_pending_count = 0
        logger.info("统计报告器数据已重置")
