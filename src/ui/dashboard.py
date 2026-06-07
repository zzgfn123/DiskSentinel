"""
DiskSentinel - 仪表盘页面

显示系统概览统计卡片、变化趋势图表和最近变化记录列表。
"""

import threading
from datetime import datetime, timedelta
from typing import Optional

import flet as ft

from src.utils.format import format_size, format_number, format_datetime

# ---------------------------------------------------------------------------
# 颜色常量
# ---------------------------------------------------------------------------
PRIMARY_COLOR = "#1a73e8"
SUCCESS_COLOR = "#34a853"
DANGER_COLOR = "#ea4335"
WARNING_COLOR = "#fbbc04"
BG_COLOR = "#f5f7fa"
CARD_BG = "#ffffff"
TEXT_PRIMARY = "#1f1f1f"
TEXT_SECONDARY = "#5f6368"
CARD_SHADOW = ft.BoxShadow(
    spread_radius=0,
    blur_radius=8,
    color=ft.Colors.with_opacity(0.08, "#000000"),
    offset=ft.Offset(0, 2),
)


class DashboardPage:
    """仪表盘页面：系统概览、趋势图表和最近变化记录。"""

    def __init__(self, page, db_manager, snapshot_engine, watcher, scheduler, reporter):
        """
        初始化仪表盘页面。

        Args:
            page: Flet Page 实例
            db_manager: DatabaseManager 实例
            snapshot_engine: SnapshotEngine 实例
            watcher: FileWatcher 实例
            scheduler: ScanScheduler 实例
            reporter: ReportGenerator 实例
        """
        self.page = page
        self.db = db_manager
        self.snapshot_engine = snapshot_engine
        self.watcher = watcher
        self.scheduler = scheduler
        self.reporter = reporter

        # ---------- 缓存的统计数据 ----------
        self._stats: dict = {}
        self._recent_changes: list = []
        self._trend_data: list = []

        # ---------- UI 组件引用（后续 build 时填充）----------
        self._stat_cards: dict[str, ft.Container] = {}
        self._chart: Optional[ft.BarChart] = None
        self._changes_list: Optional[ft.Column] = None
        self._refresh_btn: Optional[ft.IconButton] = None
        self._root_container: Optional[ft.Container] = None

        # 首次加载数据
        self._load_data()

    # ==================================================================
    # 数据加载
    # ==================================================================

    def _load_data(self):
        """从数据库加载仪表盘所需的所有数据。"""
        try:
            self._stats = self.db.get_dashboard_stats()
        except Exception:
            self._stats = {
                "total_configs": 0,
                "total_snapshots": 0,
                "total_files": 0,
                "total_size": 0,
                "changes_today": 0,
                "watch_events_today": 0,
                "last_scan_time": None,
            }

        self._load_recent_changes()
        self._load_trend_data()

    def _load_recent_changes(self):
        """加载最近 10 条变化记录。"""
        try:
            cursor = self.db._execute(
                """
                SELECT c.id, c.change_type, c.path, c.size, c.old_size, c.created_at
                FROM changes c
                ORDER BY c.created_at DESC
                LIMIT 10
                """
            )
            self._recent_changes = [dict(row) for row in cursor.fetchall()]
        except Exception:
            self._recent_changes = []

    def _load_trend_data(self):
        """加载最近 7 天的变化趋势数据。"""
        self._trend_data = []
        try:
            cursor = self.db._execute(
                """
                SELECT
                    date(created_at) AS day,
                    COUNT(*) AS change_count,
                    COALESCE(SUM(
                        CASE WHEN change_type = 'added' THEN size
                             WHEN change_type = 'removed' THEN -old_size
                             ELSE size - old_size
                        END
                    ), 0) AS size_delta
                FROM changes
                WHERE created_at >= date('now', 'localtime', '-6 days')
                GROUP BY date(created_at)
                ORDER BY day
                """
            )
            rows = cursor.fetchall()
            # 填充完整的 7 天数据（包括没有变化的日期）
            day_map = {row["day"]: dict(row) for row in rows}
            today = datetime.now().date()
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                key = d.isoformat()
                if key in day_map:
                    self._trend_data.append(day_map[key])
                else:
                    self._trend_data.append({
                        "day": key,
                        "change_count": 0,
                        "size_delta": 0,
                    })
        except Exception:
            # 降级：生成空趋势数据
            today = datetime.now().date()
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                self._trend_data.append({
                    "day": d.isoformat(),
                    "change_count": 0,
                    "size_delta": 0,
                })

    # ==================================================================
    # 今日容量变化计算
    # ==================================================================

    def _get_today_size_delta(self) -> int:
        """计算今日的总容量变化（字节）。"""
        try:
            row = self.db._execute(
                """
                SELECT COALESCE(SUM(
                    CASE WHEN change_type = 'added' THEN size
                         WHEN change_type = 'removed' THEN -old_size
                         ELSE size - old_size
                    END
                ), 0) AS delta
                FROM changes
                WHERE date(created_at) = date('now','localtime')
                """
            ).fetchone()
            return row["delta"] if row else 0
        except Exception:
            return 0

    # ==================================================================
    # UI 构建
    # ==================================================================

    def build(self) -> ft.Control:
        """构建并返回仪表盘页面 UI。"""
        self._stat_cards = {}
        today_delta = self._get_today_size_delta()

        # ---------- 统计卡片行 ----------
        cards_row = ft.Row(
            [
                self._build_stat_card(
                    key="configs",
                    icon=ft.Icons.FOLDER_OUTLINED,
                    icon_color=PRIMARY_COLOR,
                    title="监控路径",
                    value=str(self._stats.get("total_configs", 0)),
                    subtitle=f"共 {self._stats.get('total_snapshots', 0)} 次扫描",
                ),
                self._build_stat_card(
                    key="scans",
                    icon=ft.Icons.SCAN_OUTLINED,
                    icon_color="#7c4dff",
                    title="总扫描次数",
                    value=format_number(self._stats.get("total_snapshots", 0)),
                    subtitle=f"监控 {format_number(self._stats.get('total_files', 0))} 个文件",
                ),
                self._build_stat_card(
                    key="changes_today",
                    icon=ft.Icons.SYNC_ALT,
                    icon_color=SUCCESS_COLOR,
                    title="今日文件变化",
                    value=format_number(self._stats.get("changes_today", 0)),
                    subtitle="次文件变动",
                ),
                self._build_stat_card(
                    key="size_delta",
                    icon=ft.Icons.STORAGE_OUTLINED,
                    icon_color=WARNING_COLOR if today_delta >= 0 else DANGER_COLOR,
                    title="今日容量变化",
                    value=format_size(abs(today_delta)),
                    subtitle="增加" if today_delta >= 0 else "减少",
                ),
                self._build_stat_card(
                    key="last_scan",
                    icon=ft.Icons.SCHEDULE,
                    icon_color="#0097a7",
                    title="最近扫描时间",
                    value=self._format_last_scan_time(),
                    subtitle="上次快照扫描",
                ),
            ],
            wrap=True,
            spacing=16,
            run_spacing=12,
        )

        # ---------- 趋势图表 + 最近变化 并排 ----------
        chart_section = self._build_chart_section()
        changes_section = self._build_changes_section()

        middle_row = ft.Row(
            [
                ft.Container(
                    content=chart_section,
                    expand=3,
                    bgcolor=CARD_BG,
                    border_radius=12,
                    padding=20,
                    shadow=CARD_SHADOW,
                ),
                ft.Container(
                    content=changes_section,
                    expand=2,
                    bgcolor=CARD_BG,
                    border_radius=12,
                    padding=20,
                    shadow=CARD_SHADOW,
                ),
            ],
            spacing=16,
            expand=True,
        )

        # ---------- 根容器 ----------
        self._root_container = ft.Column(
            [
                # 标题栏
                ft.Row(
                    [
                        ft.Text(
                            "📊 仪表盘概览",
                            size=22,
                            weight=ft.FontWeight.BOLD,
                            color=TEXT_PRIMARY,
                        ),
                        ft.Container(expand=True),
                        self._build_refresh_button(),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Container(height=16),
                cards_row,
                ft.Container(height=16),
                middle_row,
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        return self._root_container

    # ------------------------------------------------------------------
    # 统计卡片
    # ------------------------------------------------------------------

    @staticmethod
    def _build_stat_card(
        key: str, icon, icon_color: str, title: str, value: str, subtitle: str
    ) -> ft.Container:
        """构建单个统计卡片。"""
        return ft.Container(
            key=f"card_{key}",
            content=ft.Row(
                [
                    # 图标区域
                    ft.Container(
                        content=ft.Icon(icon, size=28, color=icon_color),
                        bgcolor=ft.Colors.with_opacity(0.12, icon_color),
                        border_radius=10,
                        padding=10,
                        alignment=ft.alignment.center,
                    ),
                    ft.Container(width=12),
                    # 文本区域
                    ft.Column(
                        [
                            ft.Text(
                                title,
                                size=12,
                                color=TEXT_SECONDARY,
                            ),
                            ft.Text(
                                value,
                                size=20,
                                weight=ft.FontWeight.BOLD,
                                color=TEXT_PRIMARY,
                            ),
                            ft.Text(
                                subtitle,
                                size=11,
                                color=TEXT_SECONDARY,
                            ),
                        ],
                        spacing=2,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=CARD_BG,
            border_radius=12,
            padding=ft.padding.symmetric(horizontal=16, vertical=14),
            shadow=CARD_SHADOW,
            expand=True,
            min_width=180,
        )

    # ------------------------------------------------------------------
    # 刷新按钮
    # ------------------------------------------------------------------

    def _build_refresh_button(self) -> ft.Control:
        """构建刷新按钮。"""
        self._refresh_btn = ft.IconButton(
            icon=ft.Icons.REFRESH,
            icon_color=PRIMARY_COLOR,
            tooltip="刷新仪表盘",
            on_click=self._on_refresh,
        )
        return self._refresh_btn

    # ------------------------------------------------------------------
    # 趋势图表
    # ------------------------------------------------------------------

    def _build_chart_section(self) -> ft.Control:
        """构建变化趋势柱状图。"""
        bars = []
        for item in self._trend_data:
            day_label = item["day"][5:]  # MM-DD
            count = item["change_count"]
            bars.append(
                ft.BarChartGroup(
                    x=0,
                    bar_rods=[
                        ft.BarChartRod(
                            from_y=0,
                            to_y=count,
                            width=28,
                            color=PRIMARY_COLOR,
                            tooltip=f"{day_label}: {count} 次变化",
                            border_radius=4,
                        ),
                    ],
                )
            )

        # 生成底部标签
        bottom_axis_labels = []
        for item in self._trend_data:
            day_label = item["day"][5:]
            bottom_axis_labels.append(
                ft.ChartAxisLabel(
                    value=self._trend_data.index(item),
                    text=ft.Text(day_label, size=11, color=TEXT_SECONDARY),
                )
            )

        # 计算 Y 轴最大值
        max_count = max((item["change_count"] for item in self._trend_data), default=1)
        max_count = max(max_count, 1)

        self._chart = ft.BarChart(
            bar_groups=bars if bars else [ft.BarChartGroup(x=0, bar_rods=[])],
            groups_space=12,
            animate=ft.ChartAnimation(400, ft.AnimationCurve.EASE_OUT),
            left_axis=ft.ChartAxis(
                labels_size=40,
                title=ft.Text("变化数", size=11, color=TEXT_SECONDARY),
            ),
            bottom_axis=ft.ChartAxis(
                labels=bottom_axis_labels if bottom_axis_labels else None,
                labels_size=32,
            ),
            tooltip_bgcolor=ft.Colors.with_opacity(0.9, TEXT_PRIMARY),
            expand=True,
            interactive=True,
        )

        return ft.Column(
            [
                ft.Text(
                    "📈 近 7 天变化趋势",
                    size=15,
                    weight=ft.FontWeight.BOLD,
                    color=TEXT_PRIMARY,
                ),
                ft.Container(height=8),
                ft.Container(
                    content=self._chart,
                    expand=True,
                ),
            ],
            expand=True,
        )

    # ------------------------------------------------------------------
    # 最近变化记录
    # ------------------------------------------------------------------

    def _build_changes_section(self) -> ft.Control:
        """构建最近变化记录列表。"""
        items = []
        if not self._recent_changes:
            items.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.INBOX_OUTLINED, size=40, color=TEXT_SECONDARY),
                            ft.Text("暂无变化记录", size=13, color=TEXT_SECONDARY),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    alignment=ft.alignment.center,
                    padding=20,
                )
            )
        else:
            for change in self._recent_changes:
                change_type = change.get("change_type", "")
                path = change.get("path", "")
                size = change.get("size", 0)
                created_at = change.get("created_at", "")

                # 变化类型颜色和标签
                type_config = self._get_change_type_config(change_type)

                # 截断路径显示
                display_path = path
                if len(display_path) > 50:
                    display_path = "…" + display_path[-49:]

                items.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(
                                    content=ft.Icon(
                                        type_config["icon"],
                                        size=16,
                                        color=type_config["color"],
                                    ),
                                    width=24,
                                    alignment=ft.alignment.center,
                                ),
                                ft.Column(
                                    [
                                        ft.Text(
                                            display_path,
                                            size=12,
                                            color=TEXT_PRIMARY,
                                            max_lines=1,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        ),
                                        ft.Row(
                                            [
                                                ft.Container(
                                                    content=ft.Text(
                                                        type_config["label"],
                                                        size=10,
                                                        color=ft.Colors.WHITE,
                                                    ),
                                                    bgcolor=type_config["color"],
                                                    border_radius=4,
                                                    padding=ft.padding.symmetric(
                                                        horizontal=6, vertical=1
                                                    ),
                                                ),
                                                ft.Text(
                                                    format_size(size) if size else "",
                                                    size=10,
                                                    color=TEXT_SECONDARY,
                                                ),
                                                ft.Text(
                                                    format_datetime(created_at) if created_at else "",
                                                    size=10,
                                                    color=TEXT_SECONDARY,
                                                ),
                                            ],
                                            spacing=8,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                            ],
                            spacing=4,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        padding=ft.padding.symmetric(vertical=6),
                        border=ft.border.only(
                            bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.06, TEXT_PRIMARY))
                        ),
                    )
                )

        self._changes_list = ft.Column(items, spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)

        return ft.Column(
            [
                ft.Text(
                    "🕐 最近变化记录",
                    size=15,
                    weight=ft.FontWeight.BOLD,
                    color=TEXT_PRIMARY,
                ),
                ft.Container(height=8),
                self._changes_list,
            ],
            expand=True,
        )

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _get_change_type_config(change_type: str) -> dict:
        """返回变化类型对应的图标、颜色和标签。"""
        configs = {
            "added": {"icon": ft.Icons.ADD_CIRCLE_OUTLINE, "color": SUCCESS_COLOR, "label": "新增"},
            "removed": {"icon": ft.Icons.REMOVE_CIRCLE_OUTLINE, "color": DANGER_COLOR, "label": "删除"},
            "modified": {"icon": ft.Icons.EDIT_OUTLINED, "color": WARNING_COLOR, "label": "修改"},
            "moved": {"icon": ft.Icons.DRIVE_FILE_RENAME_OUTLINE_OUTLINED, "color": PRIMARY_COLOR, "label": "移动"},
        }
        return configs.get(change_type, {"icon": ft.Icons.HELP_OUTLINE, "color": TEXT_SECONDARY, "label": change_type})

    def _format_last_scan_time(self) -> str:
        """格式化最近扫描时间显示。"""
        last_time = self._stats.get("last_scan_time")
        if last_time:
            return format_datetime(last_time)
        return "暂无扫描"

    # ==================================================================
    # 刷新
    # ==================================================================

    def refresh(self):
        """重新加载数据并刷新仪表盘 UI。"""
        self._load_data()
        # 重新构建整个页面内容
        if self._root_container:
            new_content = self.build()
            # 通知外层 app.py 替换内容
            if self.page:
                # 找到 _content_area 容器并替换
                self.page.update()

    def _on_refresh(self, e):
        """刷新按钮点击回调（后台线程）。"""
        self._refresh_btn.icon = ft.Icons.HOURGLASS_TOP
        self._refresh_btn.disabled = True
        self.page.update()

        def _do_refresh():
            self._load_data()
            # 在主线程更新 UI
            self._refresh_btn.icon = ft.Icons.REFRESH
            self._refresh_btn.disabled = False
            # 重建整个仪表盘内容
            self._rebuild_in_place()

        threading.Thread(target=_do_refresh, daemon=True).start()

    def _rebuild_in_place(self):
        """在主线程中就地重建仪表盘内容。"""
        # 找到包含仪表盘的父容器并替换
        # 由于 NavigationRail 布局由 app.py 管理，
        # 我们直接替换 root_container 的子控件
        today_delta = self._get_today_size_delta()

        def _update_ui():
            new_content = self.build()
            # 遍历 page 控件树找到 content_area
            self._replace_content(new_content)
            self.page.update()

        self.page.run_thread(lambda: None)  # 确保在主线程执行
        # 使用 page 上的方法确保线程安全
        self.page.overlay.append(ft.SnackBar(
            content=ft.Text("仪表盘已刷新", color=ft.Colors.WHITE),
            bgcolor=SUCCESS_COLOR,
            duration=2000,
        ))
        self._load_data()
        _update_ui()

    def _replace_content(self, new_content: ft.Control):
        """替换当前页面内容。"""
        # 找到 Row 中的 content_area (第三个子控件)
        for ctrl in self.page.controls:
            if isinstance(ctrl, ft.Row) and len(ctrl.controls) >= 3:
                content_area = ctrl.controls[2]
                if isinstance(content_area, ft.Container):
                    content_area.content = new_content
                    break
