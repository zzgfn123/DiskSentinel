"""
DiskSentinel - 设置页面

提供数据管理（保留天数、清理、数据库大小）和关于信息。
"""

import json
import logging
import os
from pathlib import Path

import flet as ft

from src.core.database import DatabaseManager
from src.utils.format import format_size

logger = logging.getLogger(__name__)

# ── 颜色常量 ──────────────────────────────────────────────────────────────────
_CLR_PRIMARY = "#1a73e8"
_CLR_DANGER = "#ea4335"
_CLR_SUCCESS = "#34a853"
_CLR_WARNING = "#f9ab00"
_CLR_BG_CARD = "#ffffff"
_CLR_TEXT = "#333333"
_CLR_TEXT_LIGHT = "#888888"
_CLR_BG_SECTION = "#f5f7fa"

# 默认数据库路径
_DEFAULT_DB_PATH = os.path.join(Path.home(), ".disksentinel", "data.db")
_DEFAULT_CONFIG_PATH = os.path.join(Path.home(), ".disksentinel", "config.json")


class SettingsPage:
    """设置页面：数据管理与应用信息。"""

    def __init__(self, page: ft.Page, db: DatabaseManager):
        self.page = page
        self.db = db

        # 状态
        self._db_size_text: ft.Text | None = None
        self._retention_dropdown: ft.Dropdown | None = None

        # UI 引用
        self._snack_bar: ft.SnackBar | None = None

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def build(self) -> ft.Control:
        """构建并返回设置页面的完整 UI。"""
        db_size = self._get_db_size()

        return ft.Container(
            content=ft.Column(
                [
                    # ── 标题栏 ──
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.SETTINGS, color=_CLR_PRIMARY, size=28),
                            ft.Text(
                                "设置",
                                size=22,
                                weight=ft.FontWeight.BOLD,
                                color=_CLR_TEXT,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Divider(height=1, color="#e0e0e0"),

                    # ── 可滚动内容 ──
                    ft.Column(
                        [
                            self._build_data_management_section(db_size),
                            ft.Container(height=16),
                            self._build_export_import_section(),
                            ft.Container(height=16),
                            self._build_about_section(),
                        ],
                        scroll=ft.ScrollMode.AUTO,
                        expand=True,
                        spacing=0,
                    ),
                ],
                spacing=12,
                expand=True,
            ),
            padding=ft.padding.only(left=24, right=24, top=16, bottom=16),
            expand=True,
        )

    # ------------------------------------------------------------------
    # 数据管理
    # ------------------------------------------------------------------

    def _build_data_management_section(self, db_size: int) -> ft.Control:
        """数据管理区块：保留天数、清理按钮、数据库大小。"""

        # 保留天数下拉
        self._retention_dropdown = ft.Dropdown(
            label="数据保留天数",
            hint_text="选择数据保留期限",
            options=[
                ft.dropdown.Option("7", "7 天"),
                ft.dropdown.Option("30", "30 天"),
                ft.dropdown.Option("90", "90 天（默认）"),
                ft.dropdown.Option("365", "365 天"),
                ft.dropdown.Option("0", "永久保留"),
            ],
            value="90",
            width=240,
            dense=True,
        )

        # 数据库大小显示
        self._db_size_text = ft.Text(
            format_size(db_size),
            size=16,
            weight=ft.FontWeight.BOLD,
            color=_CLR_PRIMARY,
        )

        return ft.Container(
            content=ft.Column(
                [
                    # 标题
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.STORAGE, color=_CLR_PRIMARY, size=22),
                            ft.Text(
                                "数据管理",
                                size=17,
                                weight=ft.FontWeight.BOLD,
                                color=_CLR_TEXT,
                            ),
                        ],
                        spacing=8,
                    ),

                    ft.Container(height=12),

                    # 保留天数
                    ft.Row(
                        [
                            ft.Text("保留期限:", size=14, color=_CLR_TEXT, weight=ft.FontWeight.W_500),
                            self._retention_dropdown,
                            ft.Text(
                                "超过保留期限的扫描数据将被自动清理",
                                size=12,
                                color=_CLR_TEXT_LIGHT,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),

                    ft.Container(height=16),

                    # 清理按钮 + 数据库大小
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "清理旧数据",
                                icon=ft.Icons.DELETE_SWEEP,
                                on_click=self._on_cleanup,
                                style=ft.ButtonStyle(
                                    bgcolor=_CLR_DANGER,
                                    color=ft.Colors.WHITE,
                                    padding=ft.padding.symmetric(horizontal=16, vertical=8),
                                ),
                            ),
                            ft.Container(width=16),
                            ft.Text("数据库大小:", size=14, color=_CLR_TEXT),
                            self._db_size_text,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),

                    ft.Container(height=12),

                    # 清空全部数据按钮
                    ft.Row(
                        [
                            ft.OutlinedButton(
                                "清空全部数据",
                                icon=ft.Icons.DELETE_OUTLINE,
                                on_click=self._on_clear_all,
                                style=ft.ButtonStyle(
                                    color=_CLR_DANGER,
                                    padding=ft.padding.symmetric(horizontal=16, vertical=8),
                                ),
                            ),
                            ft.Text(
                                "删除所有快照、变化记录和监控事件（保留扫描配置）",
                                size=12,
                                color=_CLR_TEXT_LIGHT,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),

                    ft.Container(height=8),

                    ft.Text(
                        "⚠ 清理操作不可撤销，建议先导出报表备份。",
                        size=12,
                        color=_CLR_WARNING,
                    ),
                ],
                spacing=0,
            ),
            bgcolor=_CLR_BG_CARD,
            border=ft.border.all(1, "#e0e0e0"),
            border_radius=10,
            padding=20,
        )

    # ------------------------------------------------------------------
    # 导出 / 导入配置
    # ------------------------------------------------------------------

    def _build_export_import_section(self) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.SYNC_ALT, color=_CLR_PRIMARY, size=22),
                            ft.Text(
                                "配置管理",
                                size=17,
                                weight=ft.FontWeight.BOLD,
                                color=_CLR_TEXT,
                            ),
                        ],
                        spacing=8,
                    ),
                    ft.Container(height=12),
                    ft.Text(
                        "导出或导入扫描配置信息（路径、排除规则、调度设置等）。",
                        size=13,
                        color=_CLR_TEXT_LIGHT,
                    ),
                    ft.Container(height=12),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "导出配置",
                                icon=ft.Icons.FILE_DOWNLOAD,
                                on_click=self._on_export_config,
                                style=ft.ButtonStyle(
                                    bgcolor=_CLR_PRIMARY,
                                    color=ft.Colors.WHITE,
                                    padding=ft.padding.symmetric(horizontal=16, vertical=8),
                                ),
                            ),
                            ft.ElevatedButton(
                                "导入配置",
                                icon=ft.Icons.FILE_UPLOAD,
                                on_click=self._on_import_config,
                                style=ft.ButtonStyle(
                                    bgcolor=_CLR_SUCCESS,
                                    color=ft.Colors.WHITE,
                                    padding=ft.padding.symmetric(horizontal=16, vertical=8),
                                ),
                            ),
                        ],
                        spacing=12,
                    ),
                ],
                spacing=0,
            ),
            bgcolor=_CLR_BG_CARD,
            border=ft.border.all(1, "#e0e0e0"),
            border_radius=10,
            padding=20,
        )

    # ------------------------------------------------------------------
    # 关于
    # ------------------------------------------------------------------

    def _build_about_section(self) -> ft.Control:
        tech_stack_items = [
            ("Python", "3.11"),
            ("Flet", ">= 0.25.0"),
            ("SQLite", "3"),
            ("Watchdog", ">= 6.0.0"),
            ("APScheduler", ">= 3.10.0"),
        ]

        tech_rows = []
        for name, version in tech_stack_items:
            tech_rows.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=_CLR_PRIMARY),
                        ft.Text(name, size=13, color=_CLR_TEXT, weight=ft.FontWeight.W_500, width=120),
                        ft.Text(version, size=13, color=_CLR_TEXT_LIGHT),
                    ],
                    spacing=4,
                )
            )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.INFO_OUTLINE, color=_CLR_PRIMARY, size=22),
                            ft.Text(
                                "关于 DiskSentinel",
                                size=17,
                                weight=ft.FontWeight.BOLD,
                                color=_CLR_TEXT,
                            ),
                        ],
                        spacing=8,
                    ),
                    ft.Container(height=16),

                    # Logo + 版本
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(ft.Icons.SD_STORAGE, size=40, color=_CLR_PRIMARY),
                                bgcolor="#e8f0fe",
                                border_radius=12,
                                padding=10,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        "DiskSentinel",
                                        size=20,
                                        weight=ft.FontWeight.BOLD,
                                        color=_CLR_PRIMARY,
                                    ),
                                    ft.Text(
                                        "版本 1.0.0",
                                        size=13,
                                        color=_CLR_TEXT_LIGHT,
                                    ),
                                ],
                                spacing=2,
                            ),
                        ],
                        spacing=16,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),

                    ft.Container(height=12),

                    # 应用描述
                    ft.Container(
                        content=ft.Text(
                            "DiskSentinel 是一款磁盘文件监控与分析工具，支持定期扫描目录快照、"
                            "实时文件监控、变化检测与报表生成，帮助您全面掌握磁盘空间变化。",
                            size=13,
                            color=_CLR_TEXT,
                        ),
                        bgcolor=_CLR_BG_SECTION,
                        border_radius=8,
                        padding=12,
                    ),

                    ft.Container(height=16),

                    # 技术栈
                    ft.Text(
                        "技术栈",
                        size=14,
                        weight=ft.FontWeight.W_600,
                        color=_CLR_TEXT,
                    ),
                    ft.Container(height=4),
                    *tech_rows,

                    ft.Container(height=16),

                    # 版权
                    ft.Divider(height=1, color="#e0e0e0"),
                    ft.Container(height=4),
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.CODE, size=14, color=_CLR_TEXT_LIGHT),
                            ft.Text(
                                "© 2026 DiskSentinel · 开源磁盘监控工具",
                                size=12,
                                color=_CLR_TEXT_LIGHT,
                            ),
                        ],
                        spacing=4,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                spacing=0,
            ),
            bgcolor=_CLR_BG_CARD,
            border=ft.border.all(1, "#e0e0e0"),
            border_radius=10,
            padding=20,
        )

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _get_db_size(self) -> int:
        """获取数据库文件大小（字节）。"""
        try:
            db_path = self.db.db_path
            if os.path.exists(db_path):
                return os.path.getsize(db_path)
        except Exception:
            pass
        return 0

    def _get_retention_days(self) -> int:
        """从下拉框获取保留天数。"""
        val = self._retention_dropdown.value if self._retention_dropdown else "90"
        try:
            return int(val)
        except (ValueError, TypeError):
            return 90

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
            bgcolor=_CLR_DANGER if error else _CLR_SUCCESS,
            duration=3000,
        )
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def _on_cleanup(self, e) -> None:
        """清理旧数据。"""
        days = self._get_retention_days()

        if days == 0:
            self._show_snack("当前设置为永久保留，无法清理。", error=True)
            return

        # 确认对话框
        def on_confirm(ee):
            confirm_dialog.open = False
            self.page.update()
            self._do_cleanup(days)

        def on_cancel(ee):
            confirm_dialog.open = False
            self.page.update()

        confirm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("确认清理", color=_CLR_TEXT),
            content=ft.Text(
                f"即将清理 {days} 天前的所有扫描数据。\n\n此操作不可撤销，确定继续吗？",
                color=_CLR_TEXT,
            ),
            actions=[
                ft.TextButton("取消", on_click=on_cancel),
                ft.ElevatedButton(
                    "确认清理",
                    on_click=on_confirm,
                    style=ft.ButtonStyle(bgcolor=_CLR_DANGER, color=ft.Colors.WHITE),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.open(confirm_dialog)

    def _do_cleanup(self, days: int) -> None:
        """执行数据清理。"""
        try:
            result = self.db.cleanup_old_data(days_to_keep=days)
            total_deleted = (
                result.get("deleted_snapshots", 0)
                + result.get("deleted_file_entries", 0)
                + result.get("deleted_changes", 0)
                + result.get("deleted_watch_events", 0)
            )

            # 刷新数据库大小
            new_size = self._get_db_size()
            if self._db_size_text:
                self._db_size_text.value = format_size(new_size)
                self.page.update()

            self._show_snack(f"清理完成，共删除 {total_deleted} 条记录")
        except Exception as ex:
            logger.error("数据清理失败: %s", ex)
            self._show_snack(f"清理失败: {ex}", error=True)

    def _on_clear_all(self, e) -> None:
        """清空全部数据（保留 scan_configs）。"""
        def on_confirm(ee):
            confirm_dlg.open = False
            self.page.update()
            self._do_clear_all()

        def on_cancel(ee):
            confirm_dlg.open = False
            self.page.update()

        confirm_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("⚠ 清空全部数据", color=_CLR_DANGER, weight=ft.FontWeight.BOLD),
            content=ft.Text(
                "即将删除所有快照、变化记录、文件条目和监控事件。\n\n"
                "扫描配置将保留。此操作不可撤销！\n\n确定要继续吗？",
                color=_CLR_TEXT,
            ),
            actions=[
                ft.TextButton("取消", on_click=on_cancel),
                ft.ElevatedButton(
                    "确认清空",
                    on_click=on_confirm,
                    style=ft.ButtonStyle(bgcolor=_CLR_DANGER, color=ft.Colors.WHITE),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.open(confirm_dlg)

    def _do_clear_all(self) -> None:
        """执行清空全部数据。"""
        try:
            self.db._execute("DELETE FROM changes")
            self.db._execute("DELETE FROM file_entries")
            self.db._execute("DELETE FROM watch_events")
            self.db._execute("DELETE FROM snapshots")
            self.db._commit()

            # 刷新数据库大小
            new_size = self._get_db_size()
            if self._db_size_text:
                self._db_size_text.value = format_size(new_size)
                self.page.update()

            self._show_snack("已清空全部数据（扫描配置已保留）")
        except Exception as ex:
            logger.error("清空数据失败: %s", ex)
            self._show_snack(f"清空失败: {ex}", error=True)

    def _on_export_config(self, e) -> None:
        """导出扫描配置为 JSON 文件。"""
        try:
            configs = self.db.get_scan_configs()
            if not configs:
                self._show_snack("当前无扫描配置可导出", error=True)
                return

            output_dir = os.path.join(os.path.expanduser("~"), "Documents", "DiskSentinel")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, "disksentinel_config.json")

            # 清理不可序列化的字段
            export_data = []
            for cfg in configs:
                item = dict(cfg)
                # exclude_patterns 是 JSON 字符串，解析为 list
                if isinstance(item.get("exclude_patterns"), str):
                    try:
                        item["exclude_patterns"] = json.loads(item["exclude_patterns"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                export_data.append(item)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)

            self._show_snack(f"配置已导出:\n{output_path}")
        except Exception as ex:
            logger.error("导出配置失败: %s", ex)
            self._show_snack(f"导出失败: {ex}", error=True)

    def _on_import_config(self, e) -> None:
        """从 JSON 文件导入扫描配置。"""
        # 使用文件选择对话框
        def on_file_result(file_picker_event: ft.FilePickerResultEvent):
            if not file_picker_event.files:
                return
            file_path = file_picker_event.files[0].path
            self._do_import_config(file_path)

        file_picker = ft.FilePicker(on_result=on_file_result)
        self.page.overlay.append(file_picker)
        self.page.update()
        file_picker.pick_files(
            dialog_title="选择配置文件",
            allowed_extensions=["json"],
            file_type=ft.FilePickerFileType.CUSTOM,
        )

    def _do_import_config(self, file_path: str) -> None:
        """执行配置导入。"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                configs = json.load(f)

            if not isinstance(configs, list):
                self._show_snack("配置文件格式错误，应为 JSON 数组", error=True)
                return

            imported = 0
            for cfg in configs:
                if not isinstance(cfg, dict) or "path" not in cfg:
                    continue
                exclude = cfg.get("exclude_patterns", [])
                if isinstance(exclude, list):
                    exclude = json.dumps(exclude, ensure_ascii=False)
                else:
                    exclude = str(exclude)

                self.db.add_scan_config(
                    path=cfg["path"],
                    exclude_patterns=json.loads(exclude) if isinstance(exclude, str) else exclude,
                    schedule_type=cfg.get("schedule_type", "manual"),
                    schedule_value=cfg.get("schedule_value", ""),
                )
                imported += 1

            self._show_snack(f"成功导入 {imported} 条扫描配置")
        except Exception as ex:
            logger.error("导入配置失败: %s", ex)
            self._show_snack(f"导入失败: {ex}", error=True)
