"""
DiskSentinel - Flet GUI 应用主入口

提供 main(page) 函数作为 Flet 桌面应用的入口点，
初始化核心组件、构建 NavigationRail 导航布局并管理页面切换。
"""

import sys
import os
import logging

import flet as ft

# 确保 src 目录在 import 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.database import DatabaseManager
from src.core.snapshot import SnapshotEngine
from src.core.watcher import FileWatcher
from src.core.scheduler import ScanScheduler
from src.core.reporter import ReportGenerator

from src.ui.dashboard import DashboardPage
from src.ui.scanner import ScannerPage
from src.ui.monitor import MonitorPage
from src.ui.history import HistoryPage
from src.ui.settings import SettingsPage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 颜色主题常量
# ---------------------------------------------------------------------------
PRIMARY_COLOR = "#1a73e8"
BG_COLOR = "#f5f7fa"
CARD_BG = "#ffffff"
TEXT_PRIMARY = "#1f1f1f"
TEXT_SECONDARY = "#5f6368"
RAIL_BG = "#ffffff"
DIVIDER_COLOR = "#e0e0e0"

# ---------------------------------------------------------------------------
# 占位页面（尚未实现的模块）
# ---------------------------------------------------------------------------

class _PlaceholderPage:
    """占位页面，用于尚未实现的导航项。"""

    def __init__(self, title: str, icon, page: ft.Page):
        self.title = title
        self.icon = icon
        self.page = page

    def build(self) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(self.icon, size=64, color=PRIMARY_COLOR),
                    ft.Text(
                        self.title,
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color=TEXT_PRIMARY,
                    ),
                    ft.Text(
                        "该功能模块正在开发中，敬请期待…",
                        size=14,
                        color=TEXT_SECONDARY,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            expand=True,
            alignment=ft.alignment.center,
        )


# ---------------------------------------------------------------------------
# 应用核心
# ---------------------------------------------------------------------------

class DiskSentinelApp:
    """DiskSentinel Flet 应用主体，管理组件生命周期和页面导航。"""

    def __init__(self, page: ft.Page):
        self.page = page
        self._configure_page()

        # ---------- 初始化核心组件 ----------
        self.db_manager = DatabaseManager()
        self.db_manager.init_db()

        self.snapshot_engine = SnapshotEngine(self.db_manager)
        self.watcher = FileWatcher(self.db_manager)
        self.scheduler = ScanScheduler(self.db_manager, self.snapshot_engine)
        self.reporter = ReportGenerator(self.db_manager)

        # ---------- 启动后台服务 ----------
        self.scheduler.refresh_jobs()   # 从数据库加载已有的定时任务
        self.scheduler.start()          # 启动调度器

        # ---------- 构建页面 ----------
        self._pages: dict[int, object] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # 页面配置
    # ------------------------------------------------------------------

    def _configure_page(self):
        """配置 Flet 页面属性。"""
        self.page.title = "DiskSentinel - 磁盘文件变化监控"
        self.page.window.width = 1200
        self.page.window.height = 800
        self.page.window.min_width = 900
        self.page.window.min_height = 600
        self.page.bgcolor = BG_COLOR
        self.page.padding = 0
        self.page.spacing = 0
        self.page.theme = ft.Theme(
            color_scheme_seed=PRIMARY_COLOR,
            font_family="Microsoft YaHei",
        )

    # ------------------------------------------------------------------
    # 导航定义
    # ------------------------------------------------------------------

    _NAV_ITEMS = [
        (ft.Icons.DASHBOARD, "仪表盘", "dashboard"),
        (ft.Icons.FOLDER_OUTLINED, "扫描管理", "scan"),
        (ft.Icons.MONITOR_OUTLINED, "实时监控", "monitor"),
        (ft.Icons.HISTORY, "历史记录", "history"),
        (ft.Icons.SETTINGS_OUTLINED, "设置", "settings"),
    ]

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self):
        """构建完整的 UI 布局：NavigationRail + 内容区。"""

        # 导航栏目的地列表
        destinations = [
            ft.NavigationRailDestination(
                icon=icon,
                icon_content=ft.Icon(icon, color=TEXT_SECONDARY),
                selected_icon=icon,
                selected_icon_content=ft.Icon(icon, color=PRIMARY_COLOR),
                label=label,
            )
            for icon, label, _ in self._NAV_ITEMS
        ]

        self._nav_rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=80,
            min_extended_width=200,
            leading=ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.STORAGE, size=32, color=PRIMARY_COLOR),
                        ft.Text(
                            "Disk\nSentinel",
                            size=12,
                            weight=ft.FontWeight.BOLD,
                            color=PRIMARY_COLOR,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ),
                padding=ft.padding.only(top=16, bottom=8, left=0, right=0),
            ),
            destinations=destinations,
            on_change=self._on_nav_change,
            bgcolor=RAIL_BG,
            indicator_color=ft.Colors.with_opacity(0.12, PRIMARY_COLOR),
        )

        # 内容区容器 —— 用于切换页面内容
        self._content_area = ft.Container(
            expand=True,
            padding=ft.padding.all(24),
            content=self._get_page_content(0),
        )

        # 页面整体布局
        self.page.add(
            ft.Row(
                [
                    self._nav_rail,
                    ft.VerticalDivider(width=1, color=DIVIDER_COLOR),
                    self._content_area,
                ],
                expand=True,
                spacing=0,
            )
        )

    # ------------------------------------------------------------------
    # 页面切换
    # ------------------------------------------------------------------

    def _on_nav_change(self, e: ft.ControlEvent):
        """导航栏切换回调。"""
        index = e.control.selected_index
        self._nav_rail.selected_index = index
        self._content_area.content = self._get_page_content(index)
        self.page.update()

    def _get_page_content(self, index: int) -> ft.Control:
        """根据导航索引返回对应页面的 build() 结果。"""
        if index not in self._pages:
            if index == 0:
                self._pages[0] = DashboardPage(
                    page=self.page,
                    db_manager=self.db_manager,
                    snapshot_engine=self.snapshot_engine,
                    watcher=self.watcher,
                    scheduler=self.scheduler,
                    reporter=self.reporter,
                )
            elif index == 1:
                self._pages[1] = ScannerPage(
                    page=self.page,
                    db=self.db_manager,
                    snapshot_engine=self.snapshot_engine,
                )
            elif index == 2:
                self._pages[2] = MonitorPage(
                    page=self.page,
                    db=self.db_manager,
                    watcher=self.watcher,
                )
            elif index == 3:
                self._pages[3] = HistoryPage(
                    page=self.page,
                    db=self.db_manager,
                )
            elif index == 4:
                self._pages[4] = SettingsPage(
                    page=self.page,
                    db=self.db_manager,
                )
        return self._pages[index].build()


# ---------------------------------------------------------------------------
# Flet 入口函数
# ---------------------------------------------------------------------------

def main(page: ft.Page):
    """Flet 应用入口函数。"""
    DiskSentinelApp(page)


if __name__ == "__main__":
    ft.app(target=main)
