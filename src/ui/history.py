"""
DiskSentinel - 历史记录页面

顶层显示扫描记录总览列表，点击条目展开查看详细变化（新增/删除/修改的文件及容量）。
"""

import logging
import threading

import flet as ft

from src.core.database import DatabaseManager
from src.core.reporter import ReportGenerator
from src.utils.format import format_size, format_datetime, format_number, format_duration

logger = logging.getLogger(__name__)

# 颜色常量
_CLR_PRIMARY = "#1a73e8"
_CLR_SUCCESS = "#34a853"
_CLR_DANGER = "#ea4335"
_CLR_WARNING = "#fbbc04"
_CLR_TEXT = "#333333"
_CLR_TEXT_LIGHT = "#888888"
_CLR_BG = "#f5f7fa"
_CLR_CARD = "#ffffff"
_CLR_BORDER = "#e0e0e0"


class HistoryPage:
    """历史记录页面：展示扫描记录列表，点击展开详情。"""

    def __init__(self, page: ft.Page, db: DatabaseManager):
        self.page = page
        self.db = db
        self.reporter = ReportGenerator(db)

        # 展开状态
        self._expanded_id: int | None = None

        # 主列表容器
        self._list: ft.Column = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def build(self) -> ft.Control:
        """构建页面 UI。"""
        self.page.run_task(self._async_load)
        return ft.Container(
            content=ft.Column(
                [
                    # 标题栏
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.HISTORY, color=_CLR_PRIMARY, size=28),
                            ft.Text("扫描历史记录", size=22, weight=ft.FontWeight.BOLD, color=_CLR_TEXT),
                            ft.Text("点击条目展开详情", size=13, color=_CLR_TEXT_LIGHT),
                            ft.Container(expand=True),
                            ft.OutlinedButton(
                                text="删除",
                                icon=ft.Icons.DELETE_OUTLINE,
                                on_click=lambda e: self._show_delete_dialog(),
                            ),
                            ft.OutlinedButton(
                                text="刷新",
                                icon=ft.Icons.SYNC_ALT,
                                on_click=lambda e: self._load(),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(height=1, color=_CLR_BORDER),
                    self._list,
                ],
                expand=True,
            ),
            padding=ft.padding.all(24),
        )

    async def _async_load(self):
        self._load()

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------

    def _load(self):
        """加载快照列表并刷新 UI。"""
        self._list.controls.clear()
        try:
            snaps = self.db.get_snapshots(limit=100)
        except Exception as e:
            logger.error("加载快照失败: %s", e)
            snaps = []

        if not snaps:
            self._list.controls.append(self._build_empty())
            self.page.update()
            return

        for snap in snaps:
            self._list.controls.append(self._build_record(snap))

        self.page.update()

    # ------------------------------------------------------------------
    # 空状态
    # ------------------------------------------------------------------

    def _build_empty(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.INBOX, size=48, color=_CLR_TEXT_LIGHT),
                    ft.Text("暂无扫描记录", size=14, color=_CLR_TEXT_LIGHT),
                    ft.Text("请先在「扫描管理」中执行扫描", size=12, color=_CLR_TEXT_LIGHT),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            alignment=ft.alignment.center,
            padding=60,
        )

    # ------------------------------------------------------------------
    # 构建单条记录
    # ------------------------------------------------------------------

    def _build_record(self, snap: dict) -> ft.Column:
        snap_id = snap["id"]
        is_expanded = self._expanded_id == snap_id

        # 轻量 COUNT 统计
        try:
            counts = self.db.execute_query(
                "SELECT change_type, COUNT(*) as cnt FROM changes WHERE snapshot_id = ? GROUP BY change_type",
                (snap_id,),
            )
            cm = {r["change_type"]: r["cnt"] for r in counts}
            n_add = cm.get("added", 0)
            n_rem = cm.get("removed", 0)
            n_mod = cm.get("modified", 0)
        except Exception:
            n_add = n_rem = n_mod = 0

        # 概要行
        summary_row = ft.Container(
            content=ft.Row(
                [
                    # 左侧：时间 + 文件数
                    ft.Icon(ft.Icons.ACCESS_TIME, size=16, color=_CLR_PRIMARY),
                    ft.Text(
                        format_datetime(snap.get("created_at", "")),
                        size=14, weight=ft.FontWeight.W_600, color=_CLR_TEXT,
                    ),
                    ft.Text("·", size=14, color=_CLR_TEXT_LIGHT),
                    ft.Text(
                        f"{format_number(snap.get('file_count', 0))} 个文件",
                        size=13, color=_CLR_TEXT_LIGHT,
                    ),
                    ft.Text("·", size=14, color=_CLR_TEXT_LIGHT),
                    ft.Text(
                        format_size(snap.get("total_size", 0)),
                        size=13, color=_CLR_TEXT_LIGHT,
                    ),
                    ft.Text("·", size=14, color=_CLR_TEXT_LIGHT),
                    ft.Text(
                        f"耗时 {format_duration(snap.get('duration', 0))}",
                        size=13, color=_CLR_TEXT_LIGHT,
                    ),
                    # 右侧：变化徽章
                    ft.Container(expand=True),
                    self._badge(f"+{format_number(n_add)}", _CLR_SUCCESS) if n_add else ft.Container(),
                    self._badge(f"-{format_number(n_rem)}", _CLR_DANGER) if n_rem else ft.Container(),
                    self._badge(f"~{format_number(n_mod)}", _CLR_WARNING) if n_mod else ft.Container(),
                    # 展开箭头
                    ft.Icon(
                        ft.Icons.EXPAND_MORE if not is_expanded else ft.Icons.EXPAND_LESS,
                        size=20, color=_CLR_TEXT_LIGHT,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.only(left=16, right=16, top=12, bottom=12),
            border=ft.border.all(1, _CLR_PRIMARY if is_expanded else _CLR_BORDER),
            border_radius=8,
            bgcolor="#f0f4ff" if is_expanded else _CLR_CARD,
            on_click=lambda e, sid=snap_id: self._toggle(sid),
        )

        # 详情区域
        detail = ft.Container(visible=False, padding=ft.padding.only(left=8, right=8, top=4, bottom=8))
        if is_expanded:
            detail.content = self._build_detail(snap_id, n_add, n_rem, n_mod)
            detail.visible = True

        return ft.Column(
            [summary_row, detail],
            spacing=0,
        )

    def _badge(self, text: str, color: str) -> ft.Container:
        return ft.Container(
            content=ft.Text(text, size=11, weight=ft.FontWeight.W_600, color=color),
            bgcolor=f"{color}18",
            border_radius=10,
            padding=ft.padding.only(left=8, right=8, top=3, bottom=3),
        )

    # ------------------------------------------------------------------
    # 展开/收起
    # ------------------------------------------------------------------

    def _toggle(self, snap_id: int):
        if self._expanded_id == snap_id:
            self._expanded_id = None
        else:
            self._expanded_id = snap_id
        self._load()

    # ------------------------------------------------------------------
    # 构建详情面板（分 Tab 展示文件列表）
    # ------------------------------------------------------------------

    def _build_detail(self, snap_id: int, n_add: int, n_rem: int, n_mod: int) -> ft.Control:
        MAX_SHOW = 100  # 每 Tab 最多展示条数

        # 分页加载三种变化
        added = self.db.execute_query(
            "SELECT path, size, old_size FROM changes WHERE snapshot_id=? AND change_type='added' ORDER BY created_at DESC LIMIT ?",
            (snap_id, MAX_SHOW),
        )
        removed = self.db.execute_query(
            "SELECT path, size, old_size FROM changes WHERE snapshot_id=? AND change_type='removed' ORDER BY created_at DESC LIMIT ?",
            (snap_id, MAX_SHOW),
        )
        modified = self.db.execute_query(
            "SELECT path, size, old_size FROM changes WHERE snapshot_id=? AND change_type='modified' ORDER BY created_at DESC LIMIT ?",
            (snap_id, MAX_SHOW),
        )

        # 汇总大小
        add_size = sum(r.get("size", 0) for r in added)
        rem_size = sum(r.get("size", 0) for r in removed)

        # 容量变化总览
        overview = ft.Container(
            content=ft.Row(
                [
                    self._stat_box(ft.Icons.ADD_CIRCLE, "新增容量", format_size(add_size), _CLR_SUCCESS),
                    self._stat_box(ft.Icons.REMOVE_CIRCLE, "删除容量", format_size(rem_size), _CLR_DANGER),
                    self._stat_box(ft.Icons.STORAGE, "净变化", format_size(abs(add_size - rem_size)),
                                   _CLR_SUCCESS if add_size >= rem_size else _CLR_DANGER),
                ],
                spacing=12,
            ),
            padding=ft.padding.only(top=8, bottom=8),
        )

        tabs = ft.Tabs(
            selected_index=0,
            tab_alignment=ft.TabAlignment.START,
            label_color=_CLR_PRIMARY,
            unselected_label_color=_CLR_TEXT_LIGHT,
            indicator_color=_CLR_PRIMARY,
            tabs=[
                ft.Tab(
                    text=f"新增 ({format_number(n_add)})",
                    icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                    content=self._file_list(added, n_add, MAX_SHOW, _CLR_SUCCESS),
                ),
                ft.Tab(
                    text=f"删除 ({format_number(n_rem)})",
                    icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                    content=self._file_list(removed, n_rem, MAX_SHOW, _CLR_DANGER),
                ),
                ft.Tab(
                    text=f"修改 ({format_number(n_mod)})",
                    icon=ft.Icons.EDIT,
                    content=self._file_list(modified, n_mod, MAX_SHOW, _CLR_WARNING, show_old_size=True),
                ),
            ],
            expand=True,
        )

        # 导出按钮
        export_row = ft.Row(
            [
                ft.OutlinedButton(
                    text="导出 CSV",
                    icon=ft.Icons.TABLE_CHART,
                    on_click=lambda e: self._export(snap_id, "csv"),
                ),
                ft.OutlinedButton(
                    text="导出 HTML",
                    icon=ft.Icons.CODE,
                    on_click=lambda e: self._export(snap_id, "html"),
                ),
            ],
            spacing=8,
        )

        return ft.Column(
            [overview, ft.Divider(height=1), tabs, ft.Container(height=4), export_row],
            spacing=0,
            height=450,
        )

    def _stat_box(self, icon, label, value, color) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, size=18, color=color),
                    ft.Column(
                        [
                            ft.Text(label, size=11, color=_CLR_TEXT_LIGHT),
                            ft.Text(value, size=14, weight=ft.FontWeight.BOLD, color=color),
                        ],
                        spacing=2,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=_CLR_BG,
            border_radius=8,
            padding=ft.padding.only(left=12, right=12, top=8, bottom=8),
        )

    def _file_list(self, files: list, total: int, max_show: int, color: str,
                    show_old_size: bool = False) -> ft.Column:
        if not files:
            return ft.Container(
                content=ft.Text("无记录", size=13, color=_CLR_TEXT_LIGHT),
                alignment=ft.alignment.center,
                padding=30,
            )

        rows = []
        for f in files[:max_show]:
            path = f.get("path", "")
            display = path if len(path) <= 80 else "..." + path[-77:]

            if show_old_size:
                size_txt = f"{format_size(f.get('old_size',0))} → {format_size(f.get('size',0))}"
            else:
                size_txt = format_size(f.get("size", 0))

            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(width=6, height=6, bgcolor=color, border_radius=3),
                            ft.Text(display, size=11, color=_CLR_TEXT, expand=True,
                                    overflow=ft.TextOverflow.ELLIPSIS, tooltip=path),
                            ft.Text(size_txt, size=11, color=_CLR_TEXT_LIGHT),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.padding.only(left=12, top=3, right=8, bottom=3),
                )
            )

        remaining = total - len(files)
        if remaining > 0:
            rows.append(
                ft.Container(
                    content=ft.Text(
                        f"... 还有 {format_number(remaining)} 个文件未显示",
                        size=11, color=_CLR_TEXT_LIGHT, italic=True,
                    ),
                    padding=ft.padding.only(left=16, top=4, bottom=4),
                )
            )

        return ft.Column(rows, spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------

    def _export(self, snap_id: int, fmt: str):
        import os, tempfile
        out_dir = os.path.join(os.path.expanduser("~"), "Documents", "DiskSentinel")
        os.makedirs(out_dir, exist_ok=True)

        try:
            if fmt == "csv":
                path = os.path.join(out_dir, f"snapshot_{snap_id}.csv")
                self.reporter.generate_csv(snap_id, path)
            else:
                path = os.path.join(out_dir, f"snapshot_{snap_id}.html")
                self.reporter.generate_html(snap_id, path)

            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"✅ 已导出到 {path}", color=ft.Colors.WHITE),
                bgcolor=_CLR_SUCCESS,
            )
            self.page.snack_bar.open = True
            self.page.update()
        except Exception as e:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ 导出失败: {e}", color=ft.Colors.WHITE),
                bgcolor=_CLR_DANGER,
            )
            self.page.snack_bar.open = True
            self.page.update()

    # ------------------------------------------------------------------
    # 删除功能
    # ------------------------------------------------------------------

    def _show_delete_dialog(self):
        """弹出删除扫描记录的对话框。"""
        # 状态
        radio_value = ft.Ref[str]()
        radio_value.current = "all"

        dropdown = ft.Dropdown(
            label="选择快照",
            hint_text="请选择要删除的快照记录",
            options=[],
            width=400,
            visible=False,
            text_size=12,
            dense=True,
        )

        # 加载快照列表供 Dropdown 使用
        try:
            snaps = self.db.get_snapshots(limit=100)
            for snap in snaps:
                label = f"#{snap['id']}  {format_datetime(snap.get('created_at', ''))}  ({format_number(snap.get('file_count', 0))} 文件)"
                dropdown.options.append(
                    ft.dropdown.Option(str(snap["id"]), label)
                )
        except Exception:
            snaps = []

        def on_radio_change(e):
            radio_value.current = e.control.value
            dropdown.visible = (e.control.value == "single")
            self.page.update()

        radio_group = ft.RadioGroup(
            content=ft.Column(
                [
                    ft.Radio(value="all", label="删除全部记录"),
                    ft.Radio(value="single", label="选择单条删除"),
                ],
                spacing=4,
            ),
            value="all",
            on_change=on_radio_change,
        )

        def on_cancel(ee):
            dlg.open = False
            self.page.update()

        def on_confirm(ee):
            dlg.open = False
            self.page.update()
            self._do_delete(radio_value.current, dropdown.value)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("删除扫描记录", color=_CLR_TEXT, weight=ft.FontWeight.BOLD),
            content=ft.Column(
                [
                    radio_group,
                    ft.Container(height=8),
                    dropdown,
                ],
                tight=True,
                spacing=4,
                width=450,
            ),
            actions=[
                ft.TextButton("取消", on_click=on_cancel),
                ft.ElevatedButton(
                    "确认删除",
                    on_click=on_confirm,
                    style=ft.ButtonStyle(
                        bgcolor=_CLR_DANGER,
                        color=ft.Colors.WHITE,
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.open(dlg)

    def _do_delete(self, mode: str, snapshot_id_str: str | None):
        """执行删除操作。"""
        try:
            if mode == "all":
                self.db._execute("DELETE FROM changes")
                self.db._execute("DELETE FROM file_entries")
                self.db._execute("DELETE FROM watch_events")
                self.db._execute("DELETE FROM snapshots")
                self.db._commit()
                logger.info("已删除全部扫描记录")
            elif mode == "single" and snapshot_id_str:
                snap_id = int(snapshot_id_str)
                self.db._execute("DELETE FROM changes WHERE snapshot_id = ?", (snap_id,))
                self.db._execute("DELETE FROM file_entries WHERE snapshot_id = ?", (snap_id,))
                self.db._execute("DELETE FROM snapshots WHERE id = ?", (snap_id,))
                self.db._commit()
                logger.info("已删除快照 #%d", snap_id)
            else:
                return

            # 刷新列表
            self._expanded_id = None
            self._load()

            self.page.snack_bar = ft.SnackBar(
                content=ft.Text("✅ 删除成功", color=ft.Colors.WHITE),
                bgcolor=_CLR_SUCCESS,
            )
            self.page.snack_bar.open = True
            self.page.update()
        except Exception as e:
            logger.error("删除失败: %s", e)
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ 删除失败: {e}", color=ft.Colors.WHITE),
                bgcolor=_CLR_DANGER,
            )
            self.page.snack_bar.open = True
            self.page.update()
