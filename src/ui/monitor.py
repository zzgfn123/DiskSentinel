"""
DiskSentinel - 实时监控页面

提供文件系统实时监控的开关、事件日志展示、事件统计和日志导出等功能。
"""

import csv
import os
import threading
from datetime import datetime

import flet as ft

from src.core.database import DatabaseManager
from src.core.watcher import FileWatcher
from src.utils.format import format_datetime, format_number, format_size


# ---------------------------------------------------------------------------
# 颜色常量
# ---------------------------------------------------------------------------
_COLOR_PRIMARY = "#1a73e8"
_COLOR_SUCCESS = "#34a853"
_COLOR_DANGER = "#ea4335"
_COLOR_WARNING = "#fbbc04"
_COLOR_MOVED = "#9c27b0"
_COLOR_BG = "#f5f7fa"
_COLOR_CARD = "#ffffff"
_COLOR_TEXT = "#333333"
_COLOR_TEXT_SECONDARY = "#888888"
_COLOR_BORDER = "#e0e0e0"

# 事件类型颜色映射
_EVENT_COLORS = {
    "created": _COLOR_SUCCESS,
    "deleted": _COLOR_DANGER,
    "modified": _COLOR_WARNING,
    "moved": _COLOR_MOVED,
}

# 事件类型中文名
_EVENT_LABELS = {
    "created": "创建",
    "deleted": "删除",
    "modified": "修改",
    "moved": "移动",
}

# 事件类型图标
_EVENT_ICONS = {
    "created": ft.Icons.ADD_CIRCLE,
    "deleted": ft.Icons.REMOVE_CIRCLE,
    "modified": ft.Icons.EDIT,
    "moved": ft.Icons.DRIVE_FILE_MOVE,
}


class MonitorPage:
    """实时监控页面：展示文件系统变化事件。"""

    def __init__(self, page: ft.Page, db: DatabaseManager, watcher: FileWatcher):
        self.page = page
        self.db = db
        self.watcher = watcher

        # UI 控件引用
        self._monitor_switch: ft.Switch | None = None
        self._path_dropdown: ft.Dropdown | None = None
        self._event_list: ft.ListView = ft.ListView(
            expand=True, spacing=2, padding=8, auto_scroll=True
        )
        self._stat_created: ft.Text | None = None
        self._stat_deleted: ft.Text | None = None
        self._stat_modified: ft.Text | None = None
        self._stat_total: ft.Text | None = None

        # 当前选中配置
        self._selected_config_id: int | None = None

        # 事件缓冲（用于清空和导出）
        self._events: list[dict] = []

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def build(self) -> ft.Control:
        """构建并返回实时监控页面的完整 UI。"""
        return ft.Column(
            controls=[
                self._build_header(),
                ft.Divider(height=1, color=_COLOR_BORDER),
                self._build_controls(),
                self._build_stats_bar(),
                self._build_event_list_container(),
            ],
            expand=True,
        )

    # ------------------------------------------------------------------
    # 头部区域
    # ------------------------------------------------------------------

    def _build_header(self) -> ft.Container:
        """页面顶部标题栏。"""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.MONITOR, color=_COLOR_PRIMARY, size=28),
                    ft.Text(
                        "实时监控",
                        size=22,
                        weight=ft.FontWeight.BOLD,
                        color=_COLOR_TEXT,
                    ),
                    ft.Text(
                        "监控文件系统的实时变化",
                        size=13,
                        color=_COLOR_TEXT_SECONDARY,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.only(left=16, right=16, top=12, bottom=8),
        )

    # ------------------------------------------------------------------
    # 控制栏
    # ------------------------------------------------------------------

    def _build_controls(self) -> ft.Container:
        """构建监控开关、路径选择和操作按钮。"""
        # 监控开关
        self._monitor_switch = ft.Switch(
            label="开启监控",
            value=self.watcher.is_running(),
            active_color=_COLOR_SUCCESS,
            on_change=self._on_switch_toggle,
        )

        # 路径选择下拉框
        self._path_dropdown = ft.Dropdown(
            label="选择监控路径",
            width=350,
            options=[],
            hint_text="请先在「扫描管理」中添加监控路径",
            on_change=self._on_path_change,
        )
        self._refresh_path_options()

        # 操作按钮
        clear_btn = ft.OutlinedButton(
            text="清空日志",
            icon=ft.Icons.CLEAR_ALL,
            style=ft.ButtonStyle(color=_COLOR_TEXT_SECONDARY),
            on_click=self._on_clear_log,
        )

        export_btn = ft.ElevatedButton(
            text="导出日志",
            icon=ft.Icons.FILE_DOWNLOAD,
            style=ft.ButtonStyle(
                bgcolor=_COLOR_PRIMARY,
                color=ft.Colors.WHITE,
            ),
            on_click=self._on_export_log,
        )

        return ft.Container(
            content=ft.Row(
                controls=[
                    self._monitor_switch,
                    ft.Container(width=12),
                    self._path_dropdown,
                    ft.Container(expand=True),
                    clear_btn,
                    export_btn,
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.only(left=16, right=16, top=8, bottom=8),
        )

    # ------------------------------------------------------------------
    # 统计栏
    # ------------------------------------------------------------------

    def _build_stats_bar(self) -> ft.Container:
        """构建今日事件统计卡片行。"""
        self._stat_created = ft.Text("0", size=20, weight=ft.FontWeight.BOLD, color=_COLOR_SUCCESS)
        self._stat_deleted = ft.Text("0", size=20, weight=ft.FontWeight.BOLD, color=_COLOR_DANGER)
        self._stat_modified = ft.Text("0", size=20, weight=ft.FontWeight.BOLD, color=_COLOR_WARNING)
        self._stat_total = ft.Text("0", size=20, weight=ft.FontWeight.BOLD, color=_COLOR_PRIMARY)

        return ft.Container(
            content=ft.Row(
                controls=[
                    self._build_stat_card(ft.Icons.ADD_CIRCLE, "今日创建", self._stat_created, _COLOR_SUCCESS),
                    self._build_stat_card(ft.Icons.REMOVE_CIRCLE, "今日删除", self._stat_deleted, _COLOR_DANGER),
                    self._build_stat_card(ft.Icons.EDIT, "今日修改", self._stat_modified, _COLOR_WARNING),
                    self._build_stat_card(ft.Icons.LIST_ALT, "今日总计", self._stat_total, _COLOR_PRIMARY),
                ],
                spacing=12,
                alignment=ft.MainAxisAlignment.START,
            ),
            padding=ft.padding.only(left=16, right=16, top=4, bottom=4),
        )

    def _build_stat_card(self, icon: str, label: str, value_text: ft.Text, color: str) -> ft.Container:
        """构建单个统计卡片。"""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(icon, color=color, size=24),
                    ft.Column(
                        controls=[
                            ft.Text(label, size=11, color=_COLOR_TEXT_SECONDARY),
                            value_text,
                        ],
                        spacing=2,
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=_COLOR_CARD,
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            border=ft.border.all(1, _COLOR_BORDER),
            width=160,
        )

    # ------------------------------------------------------------------
    # 事件日志列表
    # ------------------------------------------------------------------

    def _build_event_list_container(self) -> ft.Container:
        """包裹事件列表的容器。"""
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.LIST, color=_COLOR_PRIMARY, size=18),
                            ft.Text(
                                "事件日志",
                                size=14,
                                weight=ft.FontWeight.W_600,
                                color=_COLOR_TEXT,
                            ),
                            ft.Container(expand=True),
                            ft.Text(
                                f"共 {len(self._events)} 条",
                                size=12,
                                color=_COLOR_TEXT_SECONDARY,
                                ref=ft.Ref[ft.Text](),  # placeholder
                            ),
                        ],
                        padding=ft.padding.only(left=8),
                    ),
                    self._event_list,
                ],
                spacing=4,
                expand=True,
            ),
            padding=ft.padding.only(left=16, right=16, bottom=16),
            expand=True,
        )

    # ------------------------------------------------------------------
    # 事件渲染
    # ------------------------------------------------------------------

    def _render_event_item(self, event: dict) -> ft.Container:
        """将单个事件渲染为一行。"""
        event_type = event.get("event_type", "modified")
        src_path = event.get("src_path", "")
        dest_path = event.get("dest_path", "")
        timestamp = event.get("timestamp", event.get("created_at", ""))
        size = event.get("size", 0)

        color = _EVENT_COLORS.get(event_type, _COLOR_TEXT_SECONDARY)
        label = _EVENT_LABELS.get(event_type, event_type)
        icon = _EVENT_ICONS.get(event_type, ft.Icons.HELP_OUTLINE)

        # 格式化时间
        time_str = ""
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%H:%M:%S")
            except (ValueError, TypeError):
                time_str = str(timestamp)[:8] if len(str(timestamp)) >= 8 else str(timestamp)

        # 路径展示
        path_display = src_path
        if event_type == "moved" and dest_path:
            path_display = f"{src_path} → {dest_path}"

        # 大小标签
        size_label = format_size(size) if size > 0 else ""

        return ft.Container(
            content=ft.Row(
                controls=[
                    # 时间
                    ft.Container(
                        content=ft.Text(time_str, size=11, color=_COLOR_TEXT_SECONDARY, font_family="monospace"),
                        width=64,
                    ),
                    # 事件类型标签
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Icon(icon, size=14, color=color),
                                ft.Text(label, size=12, weight=ft.FontWeight.W_600, color=color),
                            ],
                            spacing=4,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        bgcolor=f"{color}18",
                        border_radius=10,
                        padding=ft.padding.symmetric(horizontal=8, vertical=2),
                        width=72,
                    ),
                    # 文件路径
                    ft.Text(
                        path_display,
                        size=12,
                        color=_COLOR_TEXT,
                        expand=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    # 大小
                    ft.Text(
                        size_label,
                        size=11,
                        color=_COLOR_TEXT_SECONDARY,
                        font_family="monospace",
                        width=80,
                        text_align=ft.TextAlign.RIGHT,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            bgcolor=_COLOR_CARD,
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            border=ft.border.all(0.5, _COLOR_BORDER),
        )

    # ------------------------------------------------------------------
    # 事件回调
    # ------------------------------------------------------------------

    def on_file_event(self, event_type: str, src_path: str, dest_path: str, size: int):
        """FileWatcher 回调接口，当有新事件时由 watcher 调用。

        Args:
            event_type: 事件类型 (created/deleted/modified/moved)
            src_path: 源路径
            dest_path: 目标路径
            size: 文件大小
        """
        event = {
            "event_type": event_type,
            "src_path": src_path,
            "dest_path": dest_path,
            "size": size,
            "timestamp": datetime.now().isoformat(),
        }
        self._events.append(event)

        # 添加到列表
        item = self._render_event_item(event)
        self._event_list.controls.append(item)

        # 限制显示数量
        max_display = 500
        if len(self._event_list.controls) > max_display:
            self._event_list.controls = self._event_list.controls[-max_display:]

        # 更新统计
        self._update_stats()

        try:
            self.page.update()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 控制回调
    # ------------------------------------------------------------------

    def _on_switch_toggle(self, e):
        """开关监控。"""
        if self._monitor_switch.value:
            self._start_monitoring()
        else:
            self._stop_monitoring()

    def _start_monitoring(self):
        """启动实时监控。"""
        config_id = self._selected_config_id
        if config_id is None:
            self._show_snackbar("请先选择要监控的路径", _COLOR_WARNING)
            self._monitor_switch.value = False
            self.page.update()
            return

        # 获取配置路径
        configs = self.db.get_scan_configs()
        cfg = next((c for c in configs if c["id"] == config_id), None)
        if not cfg:
            self._show_snackbar("配置不存在", _COLOR_DANGER)
            self._monitor_switch.value = False
            self.page.update()
            return

        path = cfg["path"]
        if not os.path.isdir(path):
            self._show_snackbar(f"路径不存在: {path}", _COLOR_DANGER)
            self._monitor_switch.value = False
            self.page.update()
            return

        # 设置回调并启动
        self.watcher.callback = self.on_file_event
        self.watcher.start_watching([path], config_id)

        self._monitor_switch.label = "监控中..."
        self._monitor_switch.active_color = _COLOR_SUCCESS
        self.page.update()

        self._show_snackbar(f"已开始监控: {path}", _COLOR_SUCCESS)

    def _stop_monitoring(self):
        """停止实时监控。"""
        self.watcher.stop_watching()
        self._monitor_switch.label = "开启监控"
        self.page.update()
        self._show_snackbar("已停止监控", _COLOR_TEXT_SECONDARY)

    def _on_path_change(self, e):
        """选择监控路径。"""
        val = self._path_dropdown.value
        if val:
            self._selected_config_id = int(val)
        else:
            self._selected_config_id = None

    def _on_clear_log(self, e):
        """清空事件日志。"""
        self._events.clear()
        self._event_list.controls.clear()
        self.page.update()

    def _on_export_log(self, e):
        """导出事件日志为 CSV 文件。"""
        if not self._events:
            self._show_snackbar("暂无日志可导出", _COLOR_WARNING)
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"monitor_log_{timestamp}.csv"

        def _handle_result(result: ft.FilePickerResultEvent):
            if not result.path:
                return
            output_path = result.path
            try:
                self._write_csv(output_path)
                self._show_snackbar(f"日志已导出: {output_path}", _COLOR_SUCCESS)
            except Exception as exc:
                self._show_snackbar(f"导出失败: {exc}", _COLOR_DANGER)

        picker = ft.FilePicker(on_result=_handle_result)
        self.page.overlay.append(picker)
        self.page.update()
        picker.save_file(
            dialog_title="导出监控日志",
            file_name=default_name,
            allowed_extensions=["csv"],
        )

    def _write_csv(self, output_path: str):
        """将事件列表写入 CSV 文件。"""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["#", "时间", "事件类型", "源路径", "目标路径", "大小(字节)"])
            for idx, evt in enumerate(self._events, 1):
                writer.writerow([
                    idx,
                    evt.get("timestamp", ""),
                    _EVENT_LABELS.get(evt.get("event_type", ""), evt.get("event_type", "")),
                    evt.get("src_path", ""),
                    evt.get("dest_path", ""),
                    evt.get("size", 0),
                ])

    # ------------------------------------------------------------------
    # 统计更新
    # ------------------------------------------------------------------

    def _update_stats(self):
        """更新今日事件统计数字。"""
        today = datetime.now().strftime("%Y-%m-%d")
        created = 0
        deleted = 0
        modified = 0

        for evt in self._events:
            ts = evt.get("timestamp", "")
            if today in ts:
                et = evt.get("event_type", "")
                if et == "created":
                    created += 1
                elif et == "deleted":
                    deleted += 1
                elif et == "modified":
                    modified += 1

        total = created + deleted + modified

        if self._stat_created:
            self._stat_created.value = str(created)
        if self._stat_deleted:
            self._stat_deleted.value = str(deleted)
        if self._stat_modified:
            self._stat_modified.value = str(modified)
        if self._stat_total:
            self._stat_total.value = str(total)

    def _refresh_stats_from_db(self):
        """从数据库加载今日统计（用于初始化）。"""
        try:
            row = self.db._execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN event_type = 'created'  THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN event_type = 'deleted'  THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN event_type = 'modified' THEN 1 ELSE 0 END), 0)
                FROM watch_events
                WHERE date(created_at) = date('now','localtime')
                """
            ).fetchone()
            if row and self._stat_created:
                self._stat_created.value = str(row[0])
                self._stat_deleted.value = str(row[1])
                self._stat_modified.value = str(row[2])
                self._stat_total.value = str(row[0] + row[1] + row[2])
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 路径下拉框刷新
    # ------------------------------------------------------------------

    def _refresh_path_options(self):
        """从数据库刷新路径选择下拉框。"""
        if self._path_dropdown is None:
            return
        configs = self.db.get_scan_configs()
        self._path_dropdown.options = [
            ft.dropdown.Option(str(c["id"]), c["path"])
            for c in configs
        ]
        if configs:
            self._path_dropdown.hint_text = "请选择要监控的路径"
        else:
            self._path_dropdown.hint_text = "请先在「扫描管理」中添加监控路径"

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _show_snackbar(self, message: str, color: str = _COLOR_PRIMARY):
        """显示底部提示条。"""
        snack = ft.SnackBar(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.INFO_OUTLINE, color=ft.Colors.WHITE, size=18),
                    ft.Text(message, color=ft.Colors.WHITE, size=13),
                ],
                spacing=8,
            ),
            bgcolor=color,
            duration=3000,
        )
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()
