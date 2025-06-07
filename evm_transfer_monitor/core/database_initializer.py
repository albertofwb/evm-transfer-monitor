"""
数据库初始化模块

负责数据库连接的创建和管理
"""

from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from utils.log_utils import get_logger

logger = get_logger(__name__)


class DatabaseInitializer:
    """数据库初始化器"""
    
    def __init__(self, config: dict):
        """
        初始化数据库管理器
        
        Args:
            config: 数据库配置字典
        """
        self.config = config
        self.engine = None
        self.SessionLocal = None
        self._session = None
    
    def init_database(self) -> bool:
        """
        初始化数据库连接
        
        Returns:
            bool: 初始化是否成功
        """
        if not self.config:
            logger.warning("数据库配置为空，跳过数据库初始化")
            return False
        
        try:
            # 构建数据库URL
            db_url = self._build_database_url()
            logger.info(f"🗄️ 正在连接数据库: {self._get_safe_url(db_url)}")
            
            # 创建数据库引擎
            self.engine = create_engine(
                db_url,
                echo=False,  # 设置为True可以看到SQL语句
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,  # 连接前测试连接有效性
                pool_recycle=3600   # 1小时后回收连接
            )
            
            # 创建会话工厂
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            # 测试连接
            if self._test_connection():
                logger.info("✅ 数据库连接成功")
                return True
            else:
                logger.error("❌ 数据库连接测试失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ 数据库初始化失败: {e}")
            return False
    
    def _build_database_url(self) -> str:
        """构建数据库连接URL"""
        host = self.config.get('host', 'localhost')
        port = self.config.get('port', 5432)
        user = self.config.get('user', 'postgres')
        password = self.config.get('password', '')
        dbname = self.config.get('dbname', 'postgres')
        sslmode = self.config.get('sslmode', 'disable')
        
        return f"postgresql://{user}:{password}@{host}:{port}/{dbname}?sslmode={sslmode}"
    
    def _get_safe_url(self, url: str) -> str:
        """获取安全的URL（隐藏密码）"""
        try:
            # 简单地隐藏密码部分
            if '://' in url and '@' in url:
                protocol_part, rest = url.split('://', 1)
                if '@' in rest:
                    user_pass, host_part = rest.split('@', 1)
                    if ':' in user_pass:
                        user, _ = user_pass.split(':', 1)
                        return f"{protocol_part}://{user}:***@{host_part}"
            return url
        except:
            return "postgresql://***:***@***:****/****"
    
    def _test_connection(self) -> bool:
        """测试数据库连接"""
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text("SELECT 1"))
                return result.fetchone() is not None
        except SQLAlchemyError as e:
            logger.error(f"数据库连接测试失败: {e}")
            return False
        except Exception as e:
            logger.error(f"数据库连接测试异常: {e}")
            return False
    
    def get_session(self) -> Optional[Session]:
        """
        获取数据库会话
        
        Returns:
            Optional[Session]: 数据库会话实例
        """
        if not self.SessionLocal:
            logger.error("数据库未初始化，无法创建会话")
            return None
        
        try:
            if not self._session:
                self._session = self.SessionLocal()
            return self._session
        except Exception as e:
            logger.error(f"创建数据库会话失败: {e}")
            return None
    
    def close_session(self) -> None:
        """关闭数据库会话"""
        if self._session:
            try:
                self._session.close()
                self._session = None
                logger.debug("数据库会话已关闭")
            except Exception as e:
                logger.error(f"关闭数据库会话失败: {e}")
    
    def cleanup(self) -> None:
        """清理数据库资源"""
        self.close_session()
        
        if self.engine:
            try:
                self.engine.dispose()
                logger.info("✅ 数据库连接池已清理")
            except Exception as e:
                logger.error(f"清理数据库连接池失败: {e}")
    
    def is_connected(self) -> bool:
        """检查数据库是否连接"""
        if not self.engine:
            return False
        
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
    
    def get_stats(self) -> dict:
        """获取数据库连接统计信息"""
        if not self.engine:
            return {"connected": False}
        
        try:
            pool = self.engine.pool
            return {
                "connected": True,
                "pool_size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "invalid": pool.invalid()
            }
        except Exception as e:
            logger.error(f"获取数据库统计信息失败: {e}")
            return {"connected": True, "error": str(e)}
