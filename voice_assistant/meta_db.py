import sqlite3
import threading
import logging
from pathlib import Path
from datetime import date, timedelta
from core.config import CONFIG

logger = logging.getLogger(__name__)


class MetaDB:
    """SQLite元数据库，使用单例模式确保全局唯一连接。
    
    原本意图：追踪语音日志的转录状态
    改进：添加单例模式、线程锁、资源管理
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, db_path: str | Path = None):
        """单例模式：确保全局只有一个MetaDB实例和连接"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, db_path: str | Path = None):
        """初始化数据库连接（第一次调用时）"""
        if hasattr(self, '_initialized'):
            # 已经初始化过，跳过
            return
        
        self._state_lock = threading.RLock()
        self.path = Path(db_path or CONFIG["meta_db"])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # 使用check_same_thread=True强制单线程，由RLock来管理并发
            self._conn = sqlite3.connect(
                str(self.path),
                timeout=10,
                check_same_thread=True,
            )
            self._conn.row_factory = sqlite3.Row
            self._init()
            self._initialized = True
            logger.debug(f"MetaDB initialized at {self.path}")
        except Exception as e:
            logger.error(f"MetaDB初始化失败: {e}", exc_info=True)
            raise
    
    def _init(self):
        """创建必要的表"""
        with self._state_lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS diary_meta (
                    date TEXT PRIMARY KEY,
                    transmitted INTEGER DEFAULT 0,
                    transcribed INTEGER DEFAULT 0,
                    cleaned INTEGER DEFAULT 0,
                    error TEXT
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS core_files (
                    date TEXT,
                    filename TEXT,
                    PRIMARY KEY (date, filename)
                )
            """)
            self._conn.commit()

    def mark_transmitted(self, d: date, files: list[str] = None):
        """标记日期为已传输"""
        with self._state_lock:
            try:
                self._conn.execute(
                    "INSERT OR REPLACE INTO diary_meta (date, transmitted) VALUES (?, 1)",
                    (d.isoformat(),),
                )
                self._conn.commit()
            except sqlite3.Error as e:
                logger.error(f"mark_transmitted失败: {e}")
                raise

    def mark_transcribed(self, d: date):
        """标记日期为已转录"""
        with self._state_lock:
            try:
                self._conn.execute(
                    "UPDATE diary_meta SET transcribed = 1 WHERE date = ?",
                    (d.isoformat(),),
                )
                self._conn.commit()
            except sqlite3.Error as e:
                logger.error(f"mark_transcribed失败: {e}")
                raise

    def mark_cleaned(self, d: date):
        """标记日期为已清理"""
        with self._state_lock:
            try:
                self._conn.execute(
                    "UPDATE diary_meta SET cleaned = 1 WHERE date = ?",
                    (d.isoformat(),),
                )
                self._conn.commit()
            except sqlite3.Error as e:
                logger.error(f"mark_cleaned失败: {e}")
                raise

    def mark_preserved(self, d: date, files: list[str]):
        """标记需要保留的文件"""
        with self._state_lock:
            try:
                for f in files:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO core_files (date, filename) VALUES (?, ?)",
                        (d.isoformat(), f),
                    )
                self._conn.commit()
            except sqlite3.Error as e:
                logger.error(f"mark_preserved失败: {e}")
                raise

    def mark_error(self, d: date, error: str):
        """记录错误信息"""
        with self._state_lock:
            try:
                self._conn.execute(
                    "INSERT OR REPLACE INTO diary_meta (date, error) VALUES (?, ?)",
                    (d.isoformat(), error),
                )
                self._conn.commit()
            except sqlite3.Error as e:
                logger.error(f"mark_error失败: {e}")
                raise

    def is_transmitted(self, d: date) -> bool:
        """检查是否已传输"""
        with self._state_lock:
            try:
                row = self._conn.execute(
                    "SELECT transmitted FROM diary_meta WHERE date = ?",
                    (d.isoformat(),),
                ).fetchone()
                return row is not None and row[0] == 1
            except sqlite3.Error as e:
                logger.error(f"is_transmitted失败: {e}")
                return False

    def is_transcribed(self, d: date) -> bool:
        """检查是否已转录"""
        with self._state_lock:
            try:
                row = self._conn.execute(
                    "SELECT transcribed FROM diary_meta WHERE date = ?",
                    (d.isoformat(),),
                ).fetchone()
                return row is not None and row[0] == 1
            except sqlite3.Error as e:
                logger.error(f"is_transcribed失败: {e}")
                return False

    def pending_transmission(self) -> list[date]:
        """获取待传输的日期列表"""
        with self._state_lock:
            try:
                rows = self._conn.execute("""
                    SELECT date FROM diary_meta
                    WHERE transmitted = 1 AND transcribed = 0
                    ORDER BY date
                """).fetchall()
                return [date.fromisoformat(r[0]) for r in rows]
            except sqlite3.Error as e:
                logger.error(f"pending_transmission失败: {e}")
                return []

    def pending_transcription(self) -> list[date]:
        """获取待转录的日期列表"""
        with self._state_lock:
            try:
                rows = self._conn.execute("""
                    SELECT date FROM diary_meta
                    WHERE transmitted = 1 AND transcribed = 0
                    ORDER BY date
                """).fetchall()
                return [date.fromisoformat(r[0]) for r in rows]
            except sqlite3.Error as e:
                logger.error(f"pending_transcription失败: {e}")
                return []

    def expirable_dates(self, retention_days: int = None) -> list[date]:
        """获取可以清理的日期列表"""
        if retention_days is None:
            retention_days = CONFIG["retention_days"]
        cutoff = date.today() - timedelta(days=retention_days)
        
        with self._state_lock:
            try:
                rows = self._conn.execute("""
                    SELECT date FROM diary_meta
                    WHERE transcribed = 1 AND cleaned = 0 AND date < ?
                    ORDER BY date
                """, (cutoff.isoformat(),)).fetchall()
                return [date.fromisoformat(r[0]) for r in rows]
            except sqlite3.Error as e:
                logger.error(f"expirable_dates失败: {e}")
                return []

    def get_error(self, d: date) -> str | None:
        """获取日期的错误信息"""
        with self._state_lock:
            try:
                row = self._conn.execute(
                    "SELECT error FROM diary_meta WHERE date = ?",
                    (d.isoformat(),),
                ).fetchone()
                return row[0] if row and row[0] else None
            except sqlite3.Error as e:
                logger.error(f"get_error失败: {e}")
                return None

    def close(self):
        """显式关闭数据库连接"""
        with self._state_lock:
            if hasattr(self, '_conn') and self._conn:
                try:
                    self._conn.close()
                    logger.debug("MetaDB连接已关闭")
                except Exception as e:
                    logger.error(f"关闭MetaDB连接失败: {e}")

    def __del__(self):
        """析构时自动关闭连接"""
        try:
            if hasattr(self, '_conn') and self._conn:
                self._conn.close()
                logger.debug("MetaDB在析构时已关闭连接")
        except Exception:
            # 析构时忽略异常
            pass
