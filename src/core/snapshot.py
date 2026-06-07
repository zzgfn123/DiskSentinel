"""
DiskSentinel - 快照扫描和对比引擎

提供目录递归扫描、快照创建和快照对比功能。
"""

import os
import time
import fnmatch
import threading
from datetime import datetime
from typing import Optional, Callable, List, Dict, Any


class SnapshotEngine:
    """快照扫描和对比引擎，负责扫描目录并对比快照差异。"""

    def __init__(self, db_manager):
        """
        初始化快照引擎。

        Args:
            db_manager: database.DatabaseManager 实例，用于数据库操作。
        """
        self.db = db_manager
        self._cancel_flag = threading.Event()

    def cancel_scan(self):
        """取消正在进行的扫描。"""
        self._cancel_flag.set()

    # ------------------------------------------------------------------
    # 排除规则匹配
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_exclude_patterns(exclude_patterns: Optional[str]) -> List[str]:
        """
        将逗号分隔的排除模式字符串解析为列表。

        Args:
            exclude_patterns: 逗号分隔的模式字符串，如 "*.tmp, *.log, node_modules"

        Returns:
            模式列表，已去除首尾空白。空字符串返回空列表。
        """
        if not exclude_patterns:
            return []
        return [p.strip() for p in exclude_patterns.split(",") if p.strip()]

    @staticmethod
    def _is_excluded(path: str, name: str, patterns: List[str]) -> bool:
        """
        判断文件/目录是否应被排除。

        同时对完整路径和文件/目录名进行 fnmatch 匹配。

        Args:
            path: 完整路径
            name: 文件或目录名
            patterns: 排除模式列表

        Returns:
            True 表示应排除
        """
        for pattern in patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
            if fnmatch.fnmatch(path, pattern):
                return True
        return False

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------

    def scan_path(
        self,
        path: str,
        exclude_patterns: Optional[str] = None,
        config_id: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        """
        递归扫描指定路径，创建快照并写入数据库。

        Args:
            path: 要扫描的根目录路径
            exclude_patterns: 逗号分隔的排除模式（支持 * 通配符）
            config_id: 关联的扫描配置 ID
            progress_callback: 可选的进度回调，签名 callback(file_count, dir_count)

        Returns:
            新创建的 snapshot_id
        """
        self._cancel_flag.clear()
        patterns = self._parse_exclude_patterns(exclude_patterns)

        start_time = time.time()
        file_count = 0
        dir_count = 0
        entries: List[Dict[str, Any]] = []

        for root, dirs, files in os.walk(path):
            if self._cancel_flag.is_set():
                break

            # 按排除模式过滤目录（原地修改 dirs 列表以阻止 os.walk 进入）
            dirs[:] = [
                d for d in dirs
                if not self._is_excluded(os.path.join(root, d), d, patterns)
            ]
            dir_count += len(dirs)

            for filename in files:
                if self._cancel_flag.is_set():
                    break

                filepath = os.path.join(root, filename)

                # 排除匹配的文件
                if self._is_excluded(filepath, filename, patterns):
                    continue

                try:
                    stat = os.stat(filepath)
                except (OSError, PermissionError):
                    continue

                entries.append({
                    "path": filepath,
                    "size": stat.st_size,
                    "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
                file_count += 1

                # 定期回调进度
                if progress_callback and file_count % 200 == 0:
                    try:
                        progress_callback(file_count, dir_count)
                    except Exception:
                        pass

        # 最终进度回调
        if progress_callback:
            try:
                progress_callback(file_count, dir_count)
            except Exception:
                pass

        elapsed = time.time() - start_time

        # 写入数据库
        snapshot_id = self._save_snapshot(
            path=path,
            config_id=config_id,
            file_count=file_count,
            dir_count=dir_count,
            elapsed=elapsed,
            entries=entries,
        )
        return snapshot_id

    def _save_snapshot(
        self,
        path: str,
        config_id: Optional[int],
        file_count: int,
        dir_count: int,
        elapsed: float,
        entries: List[Dict[str, Any]],
    ) -> int:
        """
        将快照元信息和文件条目写入数据库。

        Args:
            path: 扫描路径
            config_id: 配置 ID
            file_count: 文件数
            dir_count: 目录数
            elapsed: 耗时（秒）
            entries: 文件条目列表

        Returns:
            snapshot_id
        """
        total_size = sum(e["size"] for e in entries)

        # 插入 snapshots 表
        snapshot_id = self.db.execute_insert(
            """
            INSERT INTO snapshots (config_id, file_count, total_size, duration)
            VALUES (?, ?, ?, ?)
            """,
            (config_id, file_count, total_size, round(elapsed, 3)),
        )

        # 批量插入 file_entries 表
        if entries:
            rows = [
                (snapshot_id, e["path"], e["size"], e["modified_time"])
                for e in entries
            ]
            self.db.execute_many(
                """
                INSERT INTO file_entries (snapshot_id, path, size, modified_time)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )

        return snapshot_id

    # ------------------------------------------------------------------
    # 对比
    # ------------------------------------------------------------------

    def compare_snapshots(
        self, old_snapshot_id: int, new_snapshot_id: int
    ) -> Dict[str, Any]:
        """
        对比两次快照，找出新增、删除和修改的文件。

        Args:
            old_snapshot_id: 旧快照 ID
            new_snapshot_id: 新快照 ID

        Returns:
            {
                'added':    [{'path': ..., 'size': ..., 'modified_time': ...}, ...],
                'removed':  [{'path': ..., 'size': ..., 'modified_time': ...}, ...],
                'modified': [{'path': ..., 'old_size': ..., 'new_size': ...,
                              'old_modified_time': ..., 'new_modified_time': ...}, ...],
                'summary':  {added_count, removed_count, modified_count,
                             added_size, removed_size, size_delta}
            }
        """
        old_entries = self._load_entries(old_snapshot_id)
        new_entries = self._load_entries(new_snapshot_id)

        old_map: Dict[str, Dict[str, Any]] = {e["path"]: e for e in old_entries}
        new_map: Dict[str, Dict[str, Any]] = {e["path"]: e for e in new_entries}

        old_paths = set(old_map.keys())
        new_paths = set(new_map.keys())

        # 新增文件
        added_paths = new_paths - old_paths
        added = [
            {"path": p, "size": new_map[p]["size"], "modified_time": new_map[p]["modified_time"]}
            for p in sorted(added_paths)
        ]

        # 删除文件
        removed_paths = old_paths - new_paths
        removed = [
            {"path": p, "size": old_map[p]["size"], "modified_time": old_map[p]["modified_time"]}
            for p in sorted(removed_paths)
        ]

        # 修改文件（同路径但 size 或 mtime 不同）
        common_paths = old_paths & new_paths
        modified = []
        for p in sorted(common_paths):
            o = old_map[p]
            n = new_map[p]
            if o["size"] != n["size"] or o["modified_time"] != n["modified_time"]:
                modified.append({
                    "path": p,
                    "old_size": o["size"],
                    "new_size": n["size"],
                    "old_modified_time": o["modified_time"],
                    "new_modified_time": n["modified_time"],
                })

        # 汇总
        added_size = sum(e["size"] for e in added)
        removed_size = sum(e["size"] for e in removed)

        summary = {
            "added_count": len(added),
            "removed_count": len(removed),
            "modified_count": len(modified),
            "added_size": added_size,
            "removed_size": removed_size,
            "size_delta": added_size - removed_size,
        }

        # 将变化写入 changes 表
        self._save_changes(old_snapshot_id, new_snapshot_id, added, removed, modified)

        return {
            "added": added,
            "removed": removed,
            "modified": modified,
            "summary": summary,
        }

    def _load_entries(self, snapshot_id: int) -> List[Dict[str, Any]]:
        """从数据库加载指定快照的所有文件条目。"""
        rows = self.db.execute_query(
            "SELECT path, size, modified_time FROM file_entries WHERE snapshot_id = ?",
            (snapshot_id,),
        )
        return [
            {"path": r["path"], "size": r["size"], "modified_time": r["modified_time"]}
            for r in rows
        ]

    def _save_changes(
        self,
        old_snapshot_id: int,
        new_snapshot_id: int,
        added: List[Dict[str, Any]],
        removed: List[Dict[str, Any]],
        modified: List[Dict[str, Any]],
    ) -> None:
        """将对比结果写入 changes 表。"""
        rows: List[tuple] = []

        for e in added:
            rows.append((new_snapshot_id, "added", e["path"], e["size"], 0))

        for e in removed:
            rows.append((new_snapshot_id, "removed", e["path"], 0, e["size"]))

        for e in modified:
            rows.append((new_snapshot_id, "modified", e["path"], e["new_size"], e["old_size"]))

        if rows:
            self.db.execute_many(
                """
                INSERT INTO changes
                    (snapshot_id, change_type, path, size, old_size)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )

    # ------------------------------------------------------------------
    # 一站式扫描
    # ------------------------------------------------------------------

    def run_scan(self, config_id: int) -> Dict[str, Any]:
        """
        根据配置执行完整扫描流程：读取配置 → 扫描 → 对比 → 返回结果。

        Args:
            config_id: scan_configs 表中的配置 ID

        Returns:
            {
                'snapshot_id': int,
                'comparison': dict | None,   # 首次扫描无对比结果
                'file_count': int,
                'total_size': int,
                'duration': float,
            }
        """
        # 读取配置
        rows = self.db.execute_query(
            "SELECT path, exclude_patterns FROM scan_configs WHERE id = ?",
            (config_id,),
        )
        if not rows:
            raise ValueError(f"扫描配置不存在: config_id={config_id}")

        path = rows[0]["path"]
        exclude_patterns = rows[0]["exclude_patterns"]

        # 执行扫描
        snapshot_id = self.scan_path(
            path=path,
            exclude_patterns=exclude_patterns,
            config_id=config_id,
        )

        # 获取快照信息
        snap_rows = self.db.execute_query(
            "SELECT file_count, total_size, duration FROM snapshots WHERE id = ?",
            (snapshot_id,),
        )
        file_count = snap_rows[0]["file_count"] if snap_rows else 0
        total_size = snap_rows[0]["total_size"] if snap_rows else 0
        duration = snap_rows[0]["duration"] if snap_rows else 0.0

        # 尝试找到该配置的最近一次历史快照进行对比
        comparison = None
        hist_rows = self.db.execute_query(
            """
            SELECT id FROM snapshots
            WHERE config_id = ? AND id < ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (config_id, snapshot_id),
        )
        if hist_rows:
            old_snapshot_id = hist_rows[0]["id"]
            comparison = self.compare_snapshots(old_snapshot_id, snapshot_id)

        return {
            "snapshot_id": snapshot_id,
            "comparison": comparison,
            "file_count": file_count,
            "total_size": total_size,
            "duration": duration,
        }
