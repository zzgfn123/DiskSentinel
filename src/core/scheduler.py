"""
DiskSentinel - 定时任务管理模块

使用 APScheduler 管理定时扫描任务，支持间隔、每日、每周三种调度模式。
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class ScanScheduler:
    """定时扫描调度器，基于 APScheduler 的 BackgroundScheduler。"""

    def __init__(self, db_manager, snapshot_engine, callback=None):
        """
        初始化调度器。

        Args:
            db_manager: 数据库管理器实例 (DatabaseManager)
            snapshot_engine: 快照引擎实例 (用于执行扫描)
            callback: 可选回调函数，签名为 callback(config_id, action)
                      用于通知 UI 任务状态变化（如开始扫描、扫描完成）。
        """
        self.db_manager = db_manager
        self.snapshot_engine = snapshot_engine
        self.callback = callback
        self._scheduler = BackgroundScheduler()
        self._started = False

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self):
        """启动调度器。"""
        if self._started:
            logger.warning("调度器已在运行中")
            return
        self._scheduler.start()
        self._started = True
        logger.info("调度器已启动")

    def stop(self):
        """停止调度器。"""
        if not self._started:
            return
        self._scheduler.shutdown(wait=False)
        self._started = False
        logger.info("调度器已停止")

    def is_running(self):
        """返回调度器是否正在运行。"""
        return self._started

    # ------------------------------------------------------------------
    # 任务管理
    # ------------------------------------------------------------------

    def add_job(self, config_id, schedule_type, schedule_value):
        """
        添加一个定时扫描任务。

        Args:
            config_id: 扫描配置 ID (int)
            schedule_type: 调度类型，支持:
                - 'interval': 按固定间隔（分钟）
                - 'daily':    每天定时 (HH:MM)
                - 'weekly':   每周定时 (day HH:MM)，day 为 Mon/Tue/.../Sun
            schedule_value: 调度值，格式取决于 schedule_type
                - interval: 分钟数 (int 或可转为 int 的字符串)
                - daily:    "HH:MM"
                - weekly:   "Day HH:MM"，例如 "Mon 08:00"

        Returns:
            str: APScheduler 分配的任务 ID (job_id)

        Raises:
            ValueError: 当 schedule_type 不被支持或 schedule_value 格式错误时
        """
        job_id = str(config_id)

        # 若已存在同名 job，先移除
        self.remove_job(config_id)

        trigger = self._build_trigger(schedule_type, schedule_value)

        job = self._scheduler.add_job(
            func=self._run_scan,
            trigger=trigger,
            id=job_id,
            args=[config_id],
            name=f"scan_config_{config_id}",
            replace_existing=True,
        )

        # 同步到数据库 — 更新 scan_configs 表的调度信息
        try:
            self.db_manager.execute_insert(
                """
                UPDATE scan_configs
                SET schedule_type = ?, schedule_value = ?
                WHERE id = ?
                """,
                (schedule_type, schedule_value, config_id),
            )
        except Exception as e:
            logger.error("更新 scan_configs 调度信息失败: %s", e)

        logger.info(
            "定时任务已添加: config_id=%s, type=%s, value=%s, next_run=%s",
            config_id, schedule_type, schedule_value,
            job.next_run_time if self._started else "(scheduler not started yet)",
        )
        return job.id

    def remove_job(self, config_id):
        """
        移除指定配置的定时任务。

        Args:
            config_id: 扫描配置 ID (int)
        """
        job_id = str(config_id)
        try:
            self._scheduler.remove_job(job_id)
            logger.info("定时任务已移除: config_id=%s", config_id)
        except Exception:
            # 任务可能不存在，静默忽略
            pass

    def refresh_jobs(self):
        """
        从数据库重新加载所有启用的定时任务。
        会先清除调度器中的所有现有任务，再根据 scan_configs 表重建。
        """
        # 移除所有现有任务
        self._scheduler.remove_all_jobs()
        logger.info("已清除调度器中的所有任务，开始从数据库重新加载...")

        try:
            rows = self.db_manager.fetch_all(
                """
                SELECT id, schedule_type, schedule_value
                FROM scan_configs
                WHERE enabled = 1
                  AND schedule_type IS NOT NULL
                  AND schedule_type != 'manual'
                  AND schedule_value IS NOT NULL
                  AND schedule_value != ''
                """
            )
        except Exception as e:
            logger.error("从数据库加载调度配置失败: %s", e)
            return

        count = 0
        for row in rows:
            cfg_id = row["id"]
            schedule_type = row["schedule_type"]
            schedule_value = row["schedule_value"]
            try:
                self.add_job(cfg_id, schedule_type, schedule_value)
                count += 1
            except Exception as e:
                logger.error("加载任务 config_id=%s 失败: %s", cfg_id, e)

        logger.info("任务重载完成: 共加载 %d 个定时任务", count)

    def get_next_run_time(self, config_id):
        """
        获取指定配置下一次运行时间。

        Args:
            config_id: 扫描配置 ID (int)

        Returns:
            str: 下次运行时间的 ISO 格式字符串；若任务不存在则返回空字符串。
        """
        job_id = str(config_id)
        job = self._scheduler.get_job(job_id)
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        return ""

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _build_trigger(self, schedule_type, schedule_value):
        """
        根据调度类型和值构建 APScheduler trigger。

        Args:
            schedule_type: 'interval' / 'daily' / 'weekly'
            schedule_value: 对应的调度值

        Returns:
            apscheduler 触发器实例

        Raises:
            ValueError: 类型不支持或值格式错误
        """
        if schedule_type == "interval":
            minutes = int(schedule_value)
            if minutes <= 0:
                raise ValueError(f"间隔分钟数必须大于 0，当前值: {minutes}")
            return IntervalTrigger(minutes=minutes)

        elif schedule_type == "daily":
            # schedule_value 格式: "HH:MM"
            parts = schedule_value.strip().split(":")
            if len(parts) != 2:
                raise ValueError(f"daily 格式应为 HH:MM，当前值: {schedule_value}")
            hour, minute = int(parts[0]), int(parts[1])
            return CronTrigger(hour=hour, minute=minute)

        elif schedule_type == "weekly":
            # schedule_value 格式: "Mon 08:00"
            parts = schedule_value.strip().split()
            if len(parts) != 2:
                raise ValueError(f"weekly 格式应为 'Day HH:MM'，当前值: {schedule_value}")
            day_str, time_str = parts[0], parts[1]
            day_map = {
                "Mon": "mon", "Tue": "tue", "Wed": "wed",
                "Thu": "thu", "Fri": "fri", "Sat": "sat", "Sun": "sun",
                "Monday": "mon", "Tuesday": "tue", "Wednesday": "wed",
                "Thursday": "thu", "Friday": "fri", "Saturday": "sat", "Sunday": "sun",
            }
            day_abbr = day_map.get(day_str)
            if not day_abbr:
                raise ValueError(f"不支持的星期: {day_str}")
            time_parts = time_str.split(":")
            if len(time_parts) != 2:
                raise ValueError(f"时间格式应为 HH:MM，当前值: {time_str}")
            hour, minute = int(time_parts[0]), int(time_parts[1])
            return CronTrigger(day_of_week=day_abbr, hour=hour, minute=minute)

        else:
            raise ValueError(f"不支持的 schedule_type: {schedule_type}")

    def _run_scan(self, config_id):
        """
        定时任务实际执行的扫描回调。

        Args:
            config_id: 扫描配置 ID
        """
        logger.info("定时扫描开始: config_id=%s", config_id)

        if self.callback:
            try:
                self.callback(config_id, "scan_start")
            except Exception as e:
                logger.error("回调通知失败 (scan_start): %s", e)

        try:
            self.snapshot_engine.run_scan(config_id)
            logger.info("定时扫描完成: config_id=%s", config_id)
        except Exception as e:
            logger.error("定时扫描失败: config_id=%s, error=%s", config_id, e)

        if self.callback:
            try:
                self.callback(config_id, "scan_complete")
            except Exception as e:
                logger.error("回调通知失败 (scan_complete): %s", e)
