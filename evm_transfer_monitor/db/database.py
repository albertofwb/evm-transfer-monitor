"""
数据库管理模块

负责数据库初始化、连接管理和异步操作
"""

import asyncio
import yaml
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
from pathlib import Path

from models.deposit_model import Base as DepositBase
from models.notification_models import Base as NotificationBase
from utils.log_utils import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """数据库管理器 - 负责数据库初始化和连接管理"""
    
    def __init__(self, config_path: str = "config.yml"):
        self.config_path = config_path
        self.config = self._load_config()
        self.sync_engine = None
        self.async_engine = None
        self.sync_session_factory = None
        self.async_session_factory = None
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        config_file = Path(self.config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if 'database' not in config:
            raise ValueError("配置文件中缺少database配置")
        
        return config
    
    def _get_database_url(self, async_mode: bool = False) -> str:
        """构建数据库连接URL"""
        db_config = self.config['database']
        
        driver = "asyncpg" if async_mode else "psycopg2"
        
        return (
            f"postgresql+{driver}://{db_config['user']}:{db_config['password']}"
            f"@{db_config['host']}:{db_config['port']}/{db_config['dbname']}"
            f"?sslmode={db_config.get('sslmode', 'disable')}"
        )
    
    async def initialize_database(self) -> bool:
        """初始化数据库，创建表结构"""
        try:
            logger.info("开始初始化数据库...")
            
            # 创建同步引擎用于创建表
            sync_url = self._get_database_url(async_mode=False)
            self.sync_engine = create_engine(sync_url, echo=False)
            
            # 创建所有表
            DepositBase.metadata.create_all(self.sync_engine)
            NotificationBase.metadata.create_all(self.sync_engine)
            
            logger.info("数据库表结构创建完成")
            
            # 创建异步引擎
            async_url = self._get_database_url(async_mode=True)
            self.async_engine = create_async_engine(
                async_url,
                echo=False,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600
            )
            
            # 创建会话工厂
            self.sync_session_factory = sessionmaker(bind=self.sync_engine)
            self.async_session_factory = async_sessionmaker(
                bind=self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info("数据库初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            return False
    
    def get_sync_session(self) -> Session:
        """获取同步数据库会话"""
        if not self.sync_session_factory:
            raise RuntimeError("数据库未初始化，请先调用 initialize_database()")
        return self.sync_session_factory()
    
    @asynccontextmanager
    async def get_async_session(self):
        """获取异步数据库会话（上下文管理器）"""
        if not self.async_session_factory:
            raise RuntimeError("数据库未初始化，请先调用 initialize_database()")
        
        async with self.async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    async def test_connection(self) -> bool:
        """测试数据库连接"""
        try:
            async with self.get_async_session() as session:
                result = await session.execute("SELECT 1")
                await result.fetchone()
            logger.info("数据库连接测试成功")
            return True
        except Exception as e:
            logger.error(f"数据库连接测试失败: {e}")
            return False
    
    async def close(self) -> None:
        """关闭数据库连接"""
        if self.async_engine:
            await self.async_engine.dispose()
            logger.info("异步数据库连接已关闭")
        
        if self.sync_engine:
            self.sync_engine.dispose()
            logger.info("同步数据库连接已关闭")


# 全局数据库管理器实例
_db_manager: Optional[DatabaseManager] = None


def get_database_manager() -> DatabaseManager:
    """获取数据库管理器实例（单例模式）"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


async def initialize_database() -> bool:
    """初始化数据库（便捷函数）"""
    db_manager = get_database_manager()
    return await db_manager.initialize_database()


def get_sync_session() -> Session:
    """获取同步数据库会话（便捷函数）"""
    db_manager = get_database_manager()
    return db_manager.get_sync_session()


async def get_async_session():
    """获取异步数据库会话（便捷函数）"""
    db_manager = get_database_manager()
    async with db_manager.get_async_session() as session:
        yield session


# 用于测试的示例代码
if __name__ == "__main__":
    async def main():
        # 初始化数据库
        success = await initialize_database()
        if not success:
            print("数据库初始化失败")
            return
        
        # 测试连接
        db_manager = get_database_manager()
        if await db_manager.test_connection():
            print("数据库连接正常")
        else:
            print("数据库连接异常")
        
        # 关闭连接
        await db_manager.close()
    
    asyncio.run(main())
