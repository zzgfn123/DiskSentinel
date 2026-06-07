"""
DiskSentinel - 实时文件监控模块

使用 watchdog 库监控指定路径的文件系统变化，
将事件记录到数据库并通过回调通知 UI。
"""

import os
import logging
from datetime import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileDeletedEvent, \
    FileModifiedEvent, FileMovedEvent

logger = logging.getLogger(__name__)


class FileWatcher(FileSystemEventHandler):
    """实时文件系统监控器，继承自 watchdog 的 FileSystemEventHandler。"""

    def __init__(self, db_manager, callback=None):
        """
        初始化文件监控器。

        Args:
            db_manager: 数据库管理器实例 (DatabaseManager)
            callback: 可选回调函数，签名为 callback(event_type, src_path, dest_path, size)
                      用于通知 UI 有新的文件事件发生。
        """
        super().__init__()
        self.db_manager = db_manager
        self.callback = callback
        self._observer = None
        self._watched_paths = []
        self._config_id = None
        self._running = False

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def start_watching(self, paths, config_id):
        """
        启动对指定路径的实时监控。

        Args:
            paths: 要监控的路径列表 (list[str])
            config_id: 关联的扫描配置 ID (int)
        """
        self.stop_watching()

        self._config_id = config_id
        self._watched_paths = list(paths)
        self._observer = Observer()

        for path in self._watched_paths:
            if os.path.isdir(path):
                self._observer.schedule(self, path, recursive=True)
                logger.info("已注册监控路径: %s (递归)", path)
            else:
                logger.warning("路径不存在或不是目录，跳过: %s", path)

        self._observer.daemon = True
        self._observer.start()
        self._running = True
        logger.info("实时监控已启动, config_id=%s, 路径数=%d", config_id, len(self._watched_paths))

    def stop_watching(self):
        """停止当前正在运行的监控。"""
        if self._observer is not None and self._running:
            self._observer.stop()
            try:
                self._observer.join(timeout=5)
            except Exception:
                pass
            self._running = False
            self._observer = None
            logger.info("实时监控已停止")

    def is_running(self):
        """返回当前是否正在监控。"""
        return self._running

    def get_recent_events(self, limit=50):
        """
        从数据库获取最近的监控事件。

        Args:
            limit: 返回的最大事件数量，默认 50。

        Returns:
            list[dict]: 最近的事件列表，按时间倒序排列。
        """
        try:
            rows = self.db_manager.fetch_all(
                """
                SELECT id, config_id, event_type, src_path, dest_path, size, created_at
                FROM watch_events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,)
            )
            return rows
        except Exception as e:
            logger.error("获取最近事件失败: %s", e)
            return []

    # ------------------------------------------------------------------
    # watchdog 事件处理
    # ------------------------------------------------------------------

    def on_created(self, event):
        """文件/目录创建事件处理。"""
        if event.is_directory:
            return
        src_path = event.src_path
        size = self._get_file_size(src_path)
        self._record_event("created", src_path, "", size)

    def on_deleted(self, event):
        """文件/目录删除事件处理。"""
        if event.is_directory:
            return
        src_path = event.src_path
        self._record_event("deleted", src_path, "", 0)

    def on_modified(self, event):
        """文件修改事件处理。"""
        if event.is_directory:
            return
        src_path = event.src_path
        size = self._get_file_size(src_path)
        self._record_event("modified", src_path, "", size)

    def on_moved(self, event):
        """文件/目录移动/重命名事件处理。"""
        if event.is_directory:
            return
        src_path = event.src_path
        dest_path = event.dest_path
        size = self._get_file_size(dest_path)
        self._record_event("moved", src_path, dest_path, size)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _record_event(self, event_type, src_path, dest_path="", size=0):
        """
        将事件记录写入数据库，并通过回调通知 UI。

        Args:
            event_type: 事件类型 (created/deleted/modified/moved)
            src_path: 源路径
            dest_path: 目标路径 (仅 moved 事件有值)
            size: 文件大小 (字节)
        """
        try:
            self.db_manager.execute_insert(
                """
                INSERT INTO watch_events (config_id, event_type, src_path, dest_path, size, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (self._config_id, event_type, src_path, dest_path, size, datetime.now().isoformat()),
            )
            logger.debug("事件已记录: %s %s", event_type, src_path)
        except Exception as e:
            logger.error("记录事件失败: %s | event=%s src=%s", e, event_type, src_path)

        if self.callback:
            try:
                self.callback(event_type, src_path, dest_path, size)
            except Exception as e:
                logger.error("回调通知失败: %s", e)

    @staticmethod
    def _get_file_size(path):
        """安全地获取文件大小。"""
        try:
            return os.path.getsize(path)
        except (OSError, FileNotFoundError):
            return 0
