"""
DiskSentinel - 仪表盘页面

显示系统概览统计、变化趋势和最近变化记录。
"""

import threading
from typing import Optional

import flet as ft

from src.core.database import DatabaseManager
from src.core.snapshot import SnapshotEngine
from src.core.watcher import FileWatcher
from src.core.scheduler import ScanScheduler
from src.core.reporter import ReportGenerator
from src.utils.format import format_size, format_number, format_datetime

# 颜色
PRIMARY = "#1a73e8"
SUCCESS = "#34a853"
DANGER = "#ea4335"
WARNING = "#fbbc04"
BG = "#f5f7fa"
CARD = "#ffffff"
TEXT = "#333333"
TEXT2 = "#888888"
BORDER = "#e0e0e0"


class DashboardPage:
    """仪表盘页面。"""

    def __init__(self, page, db_manager, snapshot_engine, watcher, scheduler, reporter):
        self.page = page
        self.db: DatabaseManager = db_manager
        self.engine: SnapshotEngine = snapshot_engine
        self.watcher: FileWatcher = watcher
        self.scheduler: ScanScheduler = scheduler
        self.reporter: ReportGenerator = reporter

        self._stats = {}
        self._load_data()

    def _load_data(self):
        try:
            self._stats = self.db.get_dashboard_stats()
        except Exception:
            self._stats = {
                "total_configs": 0, "total_snapshots": 0,
                "total_files": 0, "total_size": 0,
                "changes_today": 0, "watch_events_today": 0,
                "last_scan_time": None,
            }

    def build(self):
        self._load_data()
        s = self._stats

        # 统计数据
        configs = s.get("total_configs", 0)
        snaps = s.get("total_snapshots", 0)
        files = s.get("total_files", 0)
        size = s.get("total_size", 0)
        changes = s.get("changes_today", 0)
        events = s.get("watch_events_today", 0)
        last = s.get("last_scan_time")

        # 5 个统计卡片 - 不让卡片 expand，固定宽度，避免与外层 expand 冲突
        cards = ft.Row(
            [
                self._card(ft.Icons.FOLDER, "监控路径", str(configs), "已配置路径", PRIMARY),
                self._card(ft.Icons.SCANNER, "总扫描次数", str(snaps), f"共 {format_number(files)} 文件", "#7c4dff"),
                self._card(ft.Icons.SYNC_ALT, "今日变化", str(changes), "文件变化数", SUCCESS),
                self._card(ft.Icons.STORAGE, "总容量", format_size(size), "已扫描文件", WARNING),
                self._card(ft.Icons.ACCESS_TIME, "最近扫描", format_datetime(last) if last else "从未", "", DANGER),
            ],
            spacing=12,
            run_spacing=12,
        )

        # 最近变化列表
        recent = []
        try:
            rows = self.db.execute_query(
                "SELECT change_type, path, size, created_at FROM changes ORDER BY created_at DESC LIMIT 20"
            )
            for r in rows:
                color_map = {"added": SUCCESS, "removed": DANGER, "modified": WARNING}
                label_map = {"added": "+", "removed": "-", "modified": "~"}
                c = r.get("change_type", "")
                recent.append(
                    ft.Row([
                        ft.Container(
                            content=ft.Text(label_map.get(c, "?"), size=11, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                            bgcolor=color_map.get(c, TEXT2), border_radius=10,
                            width=24, height=24, alignment=ft.alignment.center,
                        ),
                        ft.Text(r.get("path", ""), size=12, color=TEXT, expand=True, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(format_size(r.get("size", 0)), size=11, color=TEXT2),
                        ft.Text(format_datetime(r.get("created_at", "")), size=11, color=TEXT2),
                    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
                )
        except Exception:
            pass

        if not recent:
            recent = [ft.Text("暂无变化记录", color=TEXT2, size=13)]

        recent_section = ft.Column([
            ft.Text("最近变化", size=16, weight=ft.FontWeight.BOLD, color=TEXT),
            ft.Divider(height=1, color=BORDER),
            *recent,
        ], spacing=6)

        # 组装页面
        return ft.Column(
            [
                # 标题行
                ft.Row([
                    ft.Icon(ft.Icons.DASHBOARD, size=24, color=PRIMARY),
                    ft.Text("仪表盘概览", size=22, weight=ft.FontWeight.BOLD, color=TEXT),
                    ft.Container(expand=True),
                    ft.IconButton(icon=ft.Icons.SYNC_ALT, tooltip="刷新", on_click=self._refresh),
                ]),
                ft.Container(height=16),
                cards,
                ft.Container(height=24),
                ft.Container(
                    content=recent_section,
                    expand=True,
                ),
            ],
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _card(self, icon, title, value, subtitle, color):
        return ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Icon(icon, size=28, color=color),
                    bgcolor=ft.Colors.with_opacity(0.12, color),
                    border_radius=10,
                    padding=10,
                    alignment=ft.alignment.center,
                ),
                ft.Container(width=12),
                ft.Column([
                    ft.Text(title, size=12, color=TEXT2),
                    ft.Text(value, size=18, weight=ft.FontWeight.BOLD, color=TEXT, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(subtitle, size=11, color=TEXT2) if subtitle else ft.Container(),
                ], spacing=2, expand=True),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
            bgcolor=CARD,
            border_radius=12,
            padding=ft.padding.only(left=14, right=14, top=12, bottom=12),
            border=ft.border.all(1, BORDER),
            width=200,
            height=80,
        )

    def _refresh(self, e=None):
        def _do():
            self._load_data()
            self.page.snack_bar = ft.SnackBar(content=ft.Text("仪表盘已刷新"), bgcolor=SUCCESS)
            self.page.snack_bar.open = True
            self.page.update()
        threading.Thread(target=_do, daemon=True).start()
