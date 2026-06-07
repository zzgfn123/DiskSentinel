"""
DiskSentinel - 历史记录页面

展示扫描快照历史列表，支持时间筛选、展开查看变化详情、导出报表。
"""

import logging
import os
from datetime import datetime

import flet as ft

from src.core.database import DatabaseManager
from src.core.reporter import ReportGenerator
from src.utils.format import format_size, format_duration, format_datetime

logger = logging.getLogger(__name__)

# ── 颜色常量 ──────────────────────────────────────────────────────────────────
_CLR_ADDED = "#34a853"
_CLR_REMOVED = "#ea4335"
_CLR_MODIFIED = "#f9ab00"
_CLR_PRIMARY = "#1a73e8"
_CLR_BG_CARD = "#ffffff"
_CLR_TEXT = "#333333"
_CLR_TEXT_LIGHT = "#888888"


class HistoryPage:
    """历史记录页面：展示扫描快照列表，可展开查看详细变化。"""

    def __init__(self, page: ft.Page, db: DatabaseManager):
        self.page = page
        self.db = db
        self.reporter = ReportGenerator(db)

        # 状态
        self._snapshots_cache: list[dict] = []
        self._expanded_snapshot_id: int | None = None
        self._changes_cache: dict[str, list[dict]] = {}  # type -> list
        self._summary_cache: dict = {}

        # 日期筛选
        self._date_from: str = ""
        self._date_to: str = ""

        # UI 引用
        self._list_container: ft.Column = ft.Column()
        self._detail_panel: ft.Container = ft.Container()
        self._date_from_field = ft.TextField(
            label="开始日期",
            hint_text="YYYY-MM-DD",
            width=160,
            dense=True,
            text_size=13,
        )
        self._date_to_field = ft.TextField(
            label="结束日期",
            hint_text="YYYY-MM-DD",
            width=160,
            dense=True,
            text_size=13,
        )
        self._snack_bar: ft.SnackBar | None = None

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def build(self) -> ft.Control:
        """构建并返回历史记录页面的完整 UI。"""
        # 加载数据
        self._load_snapshots()

        return ft.Container(
            content=ft.Column(
                [
                    # ── 标题栏 ──
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.HISTORY, color=_CLR_PRIMARY, size=28),
                            ft.Text(
                                "扫描历史记录",
                                size=22,
                                weight=ft.FontWeight.BOLD,
                                color=_CLR_TEXT,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Divider(height=1, color="#e0e0e0"),

                    # ── 筛选栏 ──
                    self._build_filter_bar(),

                    ft.Container(height=8),

                    # ── 快照列表 + 详情面板 ──
                    ft.Row(
                        [
                            # 左侧：快照列表
                            ft.Container(
                                content=ft.Column(
                                    [self._build_snapshot_list()],
                                    scroll=ft.ScrollMode.AUTO,
                                    expand=True,
                                ),
                                expand=3,
                                bgcolor=ft.Colors.TRANSPARENT,
                            ),
                            # 右侧：变化详情
                            ft.Container(
                                content=self._detail_panel,
                                expand=5,
                                bgcolor=ft.Colors.TRANSPARENT,
                            ),
                        ],
                        expand=True,
                        spacing=16,
                    ),
                ],
                spacing=12,
                expand=True,
            ),
            padding=ft.padding.only(left=24, right=24, top=16, bottom=16),
            expand=True,
        )

    # ------------------------------------------------------------------
    # 筛选栏
    # ------------------------------------------------------------------

    def _build_filter_bar(self) -> ft.Control:
        return ft.Row(
            [
                self._date_from_field,
                ft.Text("—", size=16, color=_CLR_TEXT_LIGHT),
                self._date_to_field,
                ft.Container(width=8),
                ft.ElevatedButton(
                    "筛选",
                    icon=ft.Icons.FILTER_ALT,
                    on_click=self._on_filter,
                    style=ft.ButtonStyle(
                        bgcolor=_CLR_PRIMARY,
                        color=ft.Colors.WHITE,
                        text_size=13,
                        padding=ft.padding.symmetric(horizontal=12, vertical=6),
                    ),
                ),
                ft.OutlinedButton(
                    "重置",
                    icon=ft.Icons.REFRESH,
                    on_click=self._on_reset_filter,
                    style=ft.ButtonStyle(text_size=13, padding=ft.padding.symmetric(horizontal=12, vertical=6)),
                ),
                ft.Container(expand=True),
                ft.ElevatedButton(
                    "导出 CSV",
                    icon=ft.Icons.TABLE_CHART,
                    on_click=self._on_export_csv,
                    style=ft.ButtonStyle(
                        bgcolor="#34a853",
                        color=ft.Colors.WHITE,
                        text_size=13,
                        padding=ft.padding.symmetric(horizontal=12, vertical=6),
                    ),
                ),
                ft.ElevatedButton(
                    "导出 HTML",
                    icon=ft.Icons.DESCRIPTION,
                    on_click=self._on_export_html,
                    style=ft.ButtonStyle(
                        bgcolor="#f9ab00",
                        color=ft.Colors.WHITE,
                        text_size=13,
                        padding=ft.padding.symmetric(horizontal=12, vertical=6),
                    ),
                ),
            ],
            alignment=ft.MainAxisAlignment.START,
            wrap=True,
        )

    # ------------------------------------------------------------------
    # 快照列表
    # ------------------------------------------------------------------

    def _build_snapshot_list(self) -> ft.Control:
        if not self._snapshots_cache:
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.INBOX, size=48, color=_CLR_TEXT_LIGHT),
                        ft.Text("暂无扫描记录", size=14, color=_CLR_TEXT_LIGHT),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                alignment=ft.alignment.center,
                padding=40,
            )

        items: list[ft.Control] = []
        for snap in self._snapshots_cache:
            items.append(self._build_snapshot_card(snap))

        self._list_container = ft.Column(items, spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        return self._list_container

    def _build_snapshot_card(self, snap: dict) -> ft.Control:
        is_selected = self._expanded_snapshot_id == snap["id"]

        # 统计变化数量
        changes = self.db.get_changes_for_snapshot(snap["id"])
        added = sum(1 for c in changes if c["change_type"] == "added")
        removed = sum(1 for c in changes if c["change_type"] == "removed")
        modified = sum(1 for c in changes if c["change_type"] == "modified")

        border_color = _CLR_PRIMARY if is_selected else "#e0e0e0"
        bg_color = "#f0f4ff" if is_selected else _CLR_BG_CARD

        return ft.Container(
            content=ft.Column(
                [
                    # 第一行：时间 + 路径
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.ACCESS_TIME, size=16, color=_CLR_TEXT_LIGHT),
                            ft.Text(
                                format_datetime(snap.get("created_at", "")),
                                size=13,
                                weight=ft.FontWeight.W_600,
                                color=_CLR_TEXT,
                            ),
                        ],
                        spacing=4,
                    ),
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.FOLDER, size=14, color=_CLR_TEXT_LIGHT),
                            ft.Text(
                                snap.get("config_path", "—"),
                                size=12,
                                color=_CLR_TEXT_LIGHT,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                expand=True,
                            ),
                        ],
                        spacing=4,
                    ),
                    ft.Container(height=4),
                    # 第二行：文件数 / 大小 / 耗时
                    ft.Row(
                        [
                            self._mini_stat(ft.Icons.INSERT_DRIVE_FILE, f'{snap.get("file_count", 0)} 文件'),
                            self._mini_stat(ft.Icons.DATA_USAGE, format_size(snap.get("total_size", 0))),
                            self._mini_stat(ft.Icons.TIMER, format_duration(snap.get("duration", 0))),
                        ],
                        spacing=12,
                    ),
                    ft.Container(height=4),
                    # 第三行：变化摘要
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Text(f"+{added} 新增", size=11, color=_CLR_ADDED, weight=ft.FontWeight.W_600),
                                bgcolor="#e6f4ea",
                                border_radius=6,
                                padding=ft.padding.symmetric(horizontal=8, vertical=2),
                            ),
                            ft.Container(
                                content=ft.Text(f"-{removed} 删除", size=11, color=_CLR_REMOVED, weight=ft.FontWeight.W_600),
                                bgcolor="#fce8e6",
                                border_radius=6,
                                padding=ft.padding.symmetric(horizontal=8, vertical=2),
                            ),
                            ft.Container(
                                content=ft.Text(f"~{modified} 修改", size=11, color=_CLR_MODIFIED, weight=ft.FontWeight.W_600),
                                bgcolor="#fef7e0",
                                border_radius=6,
                                padding=ft.padding.symmetric(horizontal=8, vertical=2),
                            ),
                        ],
                        spacing=6,
                    ),
                ],
                spacing=2,
            ),
            bgcolor=bg_color,
            border=ft.border.all(1.5, border_color),
            border_radius=8,
            padding=12,
            on_click=lambda e, s=snap: self._on_snapshot_click(s),
            ink=True,
        )

    @staticmethod
    def _mini_stat(icon: str, text: str) -> ft.Control:
        return ft.Row(
            [
                ft.Icon(icon, size=14, color=_CLR_TEXT_LIGHT),
                ft.Text(text, size=12, color=_CLR_TEXT),
            ],
            spacing=2,
            mainAxisSize=ft.MainAxisSize.MIN,
        )

    # ------------------------------------------------------------------
    # 详情面板（三个 Tab：新增 / 删除 / 修改）
    # ------------------------------------------------------------------

    def _build_detail_panel(self, snapshot_id: int) -> ft.Control:
        changes = self.db.get_changes_for_snapshot(snapshot_id)

        # 按类型分组
        added_files = [c for c in changes if c["change_type"] == "added"]
        removed_files = [c for c in changes if c["change_type"] == "removed"]
        modified_files = [c for c in changes if c["change_type"] == "modified"]

        # 汇总大小
        total_added_size = sum(c.get("size", 0) for c in added_files)
        total_removed_size = sum(c.get("size", 0) for c in removed_files)
        total_modified_size = sum(c.get("size", 0) for c in modified_files)

        # 构建 Tab 内容
        tabs = ft.Tabs(
            selected_index=0,
            animation_duration=200,
            tab_alignment=ft.TabAlignment.START,
            label_color=_CLR_PRIMARY,
            unselected_label_color=_CLR_TEXT_LIGHT,
            indicator_color=_CLR_PRIMARY,
            indicator_tab_size=True,
            tabs=[
                ft.Tab(
                    text=f"新增 ({len(added_files)})",
                    icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                    content=self._build_file_list_tab(
                        added_files, _CLR_ADDED, total_added_size, "总新增大小"
                    ),
                ),
                ft.Tab(
                    text=f"删除 ({len(removed_files)})",
                    icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                    content=self._build_file_list_tab(
                        removed_files, _CLR_REMOVED, total_removed_size, "总删除大小"
                    ),
                ),
                ft.Tab(
                    text=f"修改 ({len(modified_files)})",
                    icon=ft.Icons.EDIT_OUTLINED,
                    content=self._build_file_list_tab(
                        modified_files, _CLR_MODIFIED, total_modified_size, "总修改大小"
                    ),
                ),
            ],
            expand=True,
        )

        # 找到快照信息
        snap_info = next((s for s in self._snapshots_cache if s["id"] == snapshot_id), None)

        header = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SNIPPET_FOLDER, color=_CLR_PRIMARY, size=22),
                        ft.Text(
                            f"快照 #{snapshot_id} 详情",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=_CLR_TEXT,
                        ),
                        ft.Container(expand=True),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            icon_size=18,
                            on_click=lambda e: self._close_detail(),
                            tooltip="关闭详情",
                        ),
                    ],
                ),
                ft.Text(
                    f"扫描路径: {snap_info['config_path'] if snap_info else '—'}    "
                    f"时间: {format_datetime(snap_info['created_at']) if snap_info else '—'}",
                    size=12,
                    color=_CLR_TEXT_LIGHT,
                ),
                ft.Divider(height=1, color="#e0e0e0"),
            ],
            spacing=4,
        )

        return ft.Container(
            content=ft.Column(
                [header, tabs],
                spacing=0,
                expand=True,
            ),
            bgcolor=_CLR_BG_CARD,
            border=ft.border.all(1, "#e0e0e0"),
            border_radius=10,
            padding=16,
            expand=True,
        )

    def _build_file_list_tab(
        self, files: list[dict], accent_color: str, total_size: int, size_label: str
    ) -> ft.Control:
        if not files:
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=36, color="#bdbdbd"),
                        ft.Text("无变化记录", size=13, color="#bdbdbd"),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                alignment=ft.alignment.center,
                padding=40,
            )

        rows: list[ft.Control] = [
            # 表头
            ft.Container(
                content=ft.Row(
                    [
                        ft.Text("文件路径", size=12, weight=ft.FontWeight.BOLD, color=_CLR_TEXT_LIGHT, expand=True),
                        ft.Text("大小", size=12, weight=ft.FontWeight.BOLD, color=_CLR_TEXT_LIGHT, width=100),
                        ft.Text("旧大小", size=12, weight=ft.FontWeight.BOLD, color=_CLR_TEXT_LIGHT, width=100),
                    ],
                ),
                bgcolor="#f5f7fa",
                border_radius=ft.border_radius.only(top_left=6, top_right=6),
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
            ),
        ]

        for f in files:
            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Tooltip(
                                message=f.get("path", ""),
                                content=ft.Text(
                                    f.get("path", "—"),
                                    size=12,
                                    color=_CLR_TEXT,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                    expand=True,
                                ),
                            ),
                            ft.Text(
                                format_size(f.get("size", 0)),
                                size=12,
                                color=accent_color,
                                width=100,
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(
                                format_size(f.get("old_size", 0)),
                                size=12,
                                color=_CLR_TEXT_LIGHT,
                                width=100,
                            ),
                        ],
                    ),
                    border=ft.border.only(bottom=ft.BorderSide(0.5, "#eeeeee")),
                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                ),
            )

        # 汇总栏
        rows.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Text(
                            f"共 {len(files)} 个文件",
                            size=12,
                            color=_CLR_TEXT_LIGHT,
                        ),
                        ft.Container(expand=True),
                        ft.Text(
                            f"{size_label}: ",
                            size=12,
                            color=_CLR_TEXT_LIGHT,
                        ),
                        ft.Text(
                            format_size(total_size),
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color=accent_color,
                        ),
                    ],
                ),
                bgcolor="#f5f7fa",
                border_radius=ft.border_radius.only(bottom_left=6, bottom_right=6),
                padding=ft.padding.symmetric(horizontal=12, vertical=10),
            ),
        )

        return ft.Container(
            content=ft.Column(rows, spacing=0, scroll=ft.ScrollMode.AUTO),
            margin=ft.margin.only(top=8),
        )

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------

    def _load_snapshots(self) -> None:
        """从数据库加载快照列表，支持日期筛选。"""
        try:
            if self._date_from or self._date_to:
                # 带日期范围的查询
                conditions: list[str] = []
                params: list = []

                if self._date_from:
                    conditions.append("s.created_at >= ?")
                    params.append(f"{self._date_from} 00:00:00")
                if self._date_to:
                    conditions.append("s.created_at <= ?")
                    params.append(f"{self._date_to} 23:59:59")

                where_clause = " AND ".join(conditions)
                sql = f"""
                    SELECT s.*, sc.path AS config_path
                    FROM snapshots s
                    JOIN scan_configs sc ON s.config_id = sc.id
                    WHERE {where_clause}
                    ORDER BY s.created_at DESC
                    LIMIT 100
                """
                cursor = self.db._execute(sql, tuple(params))
                self._snapshots_cache = [dict(row) for row in cursor.fetchall()]
            else:
                self._snapshots_cache = self.db.get_snapshots(limit=100)
        except Exception as e:
            logger.error("加载快照列表失败: %s", e)
            self._snapshots_cache = []

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def _on_snapshot_click(self, snap: dict) -> None:
        """点击快照卡片，展示变化详情。"""
        self._expanded_snapshot_id = snap["id"]
        self._detail_panel = self._build_detail_panel(snap["id"])
        self._refresh_view()

    def _close_detail(self) -> None:
        """关闭详情面板。"""
        self._expanded_snapshot_id = None
        self._detail_panel = ft.Container()
        self._refresh_view()

    def _on_filter(self, e) -> None:
        """应用日期筛选。"""
        self._date_from = self._date_from_field.value.strip() if self._date_from_field.value else ""
        self._date_to = self._date_to_field.value.strip() if self._date_to_field.value else ""

        # 验证日期格式
        for date_str, label in [(self._date_from, "开始日期"), (self._date_to, "结束日期")]:
            if date_str:
                try:
                    datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    self._show_snack(f"{label} 格式不正确，请使用 YYYY-MM-DD", error=True)
                    return

        self._load_snapshots()
        self._expanded_snapshot_id = None
        self._detail_panel = ft.Container()
        self._refresh_view()

    def _on_reset_filter(self, e) -> None:
        """重置日期筛选。"""
        self._date_from_field.value = ""
        self._date_to_field.value = ""
        self._date_from = ""
        self._date_to = ""
        self._load_snapshots()
        self._expanded_snapshot_id = None
        self._detail_panel = ft.Container()
        self._refresh_view()

    def _on_export_csv(self, e) -> None:
        """导出当前选中快照的变化记录为 CSV。"""
        if self._expanded_snapshot_id is None:
            self._show_snack("请先选择一个快照记录", error=True)
            return

        try:
            output_dir = os.path.join(os.path.expanduser("~"), "Documents", "DiskSentinel")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"snapshot_{self._expanded_snapshot_id}_report.csv")
            result_path = self.reporter.generate_csv(self._expanded_snapshot_id, output_path)
            self._show_snack(f"CSV 报表已导出:\n{result_path}")
        except Exception as ex:
            logger.error("导出 CSV 失败: %s", ex)
            self._show_snack(f"导出失败: {ex}", error=True)

    def _on_export_html(self, e) -> None:
        """导出当前选中快照的变化记录为 HTML。"""
        if self._expanded_snapshot_id is None:
            self._show_snack("请先选择一个快照记录", error=True)
            return

        try:
            output_dir = os.path.join(os.path.expanduser("~"), "Documents", "DiskSentinel")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"snapshot_{self._expanded_snapshot_id}_report.html")
            result_path = self.reporter.generate_html(self._expanded_snapshot_id, output_path)
            self._show_snack(f"HTML 报表已导出:\n{result_path}")
        except Exception as ex:
            logger.error("导出 HTML 失败: %s", ex)
            self._show_snack(f"导出失败: {ex}", error=True)

    # ------------------------------------------------------------------
    # UI 辅助
    # ------------------------------------------------------------------

    def _refresh_view(self) -> None:
        """重建整个页面内容（简单策略：替换 page 中的 body）。"""
        # 找到主内容容器并替换
        if hasattr(self.page, "controls"):
            self.page.controls.clear()
            self.page.controls.append(self.build())
            self.page.update()

    def _show_snack(self, message: str, error: bool = False) -> None:
        """显示 SnackBar 提示。"""
        snack = ft.SnackBar(
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.ERROR_OUTLINE if error else ft.Icons.CHECK_CIRCLE_OUTLINE,
                        color=ft.Colors.WHITE,
                        size=20,
                    ),
                    ft.Text(message, color=ft.Colors.WHITE, size=13),
                ],
                spacing=8,
            ),
            bgcolor="#ea4335" if error else "#34a853",
            duration=3000,
        )
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()
