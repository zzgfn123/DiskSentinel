"""
DiskSentinel - 扫描管理页面

提供监控路径列表展示、添加/编辑/删除配置、立即扫描及进度展示等功能。
"""

import json
import threading
from datetime import datetime

import flet as ft

from src.core.database import DatabaseManager
from src.core.snapshot import SnapshotEngine
from src.utils.format import format_size, format_datetime, format_number, format_duration


# ---------------------------------------------------------------------------
# 颜色常量
# ---------------------------------------------------------------------------
_COLOR_PRIMARY = "#1a73e8"
_COLOR_SUCCESS = "#34a853"
_COLOR_WARNING = "#fbbc04"
_COLOR_DANGER = "#ea4335"
_COLOR_BG = "#f5f7fa"
_COLOR_CARD = "#ffffff"
_COLOR_TEXT = "#333333"
_COLOR_TEXT_SECONDARY = "#888888"
_COLOR_BORDER = "#e0e0e0"


class ScannerPage:
    """扫描管理页面：管理监控路径、执行扫描、查看结果。"""

    def __init__(self, page: ft.Page, db: DatabaseManager, snapshot_engine: SnapshotEngine):
        self.page = page
        self.db = db
        self.snapshot_engine = snapshot_engine

        # UI 控件引用
        self._list_view: ft.ListView = ft.ListView(expand=True, spacing=8, padding=8)
        self._progress_bars: dict[int, ft.ProgressBar] = {}  # config_id -> ProgressBar
        self._status_texts: dict[int, ft.Text] = {}           # config_id -> status Text
        self._result_bars: dict[int, ft.Container] = {}       # config_id -> result summary
        self._baseline_dropdowns: dict[int, ft.Dropdown] = {} # config_id -> baseline selector

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def build(self) -> ft.Control:
        """构建并返回扫描管理页面的完整 UI。"""
        # 延迟加载数据，确保 UI 已构建
        self.page.run_task(self._async_refresh)
        return ft.Column(
            controls=[
                self._build_header(),
                ft.Divider(height=1, color=_COLOR_BORDER),
                self._list_view,
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    async def _async_refresh(self):
        """异步刷新数据列表。"""
        self.refresh()

    def refresh(self):
        """从数据库刷新监控路径列表。"""
        self._list_view.controls.clear()
        self._progress_bars.clear()
        self._status_texts.clear()
        self._result_bars.clear()
        self._baseline_dropdowns.clear()

        configs = self.db.get_scan_configs()

        if not configs:
            self._list_view.controls.append(
                self._build_empty_placeholder()
            )
            self.page.update()
            return

        for cfg in configs:
            card = self._build_config_card(cfg)
            self._list_view.controls.append(card)

        self.page.update()

    # ------------------------------------------------------------------
    # 头部区域
    # ------------------------------------------------------------------

    def _build_header(self) -> ft.Container:
        """构建页面顶部标题栏和添加按钮。"""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.FOLDER_OPEN, color=_COLOR_PRIMARY, size=28),
                    ft.Text(
                        "扫描管理",
                        size=22,
                        weight=ft.FontWeight.BOLD,
                        color=_COLOR_TEXT,
                    ),
                    ft.Text(
                        "管理监控路径和扫描任务",
                        size=13,
                        color=_COLOR_TEXT_SECONDARY,
                    ),
                    ft.Container(expand=True),
                    ft.ElevatedButton(
                        text="添加监控路径",
                        icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                        style=ft.ButtonStyle(
                            bgcolor=_COLOR_PRIMARY,
                            color=ft.Colors.WHITE,
                            padding=ft.padding.symmetric(horizontal=16, vertical=8),
                        ),
                        on_click=self._on_add_click,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.only(left=16, right=16, top=12, bottom=8),
        )

    # ------------------------------------------------------------------
    # 空状态占位
    # ------------------------------------------------------------------

    def _build_empty_placeholder(self) -> ft.Container:
        """当没有监控路径时显示空状态提示。"""
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(ft.Icons.FOLDER_OFF_OUTLINED, size=64, color=_COLOR_TEXT_SECONDARY),
                    ft.Text(
                        "暂无监控路径",
                        size=16,
                        color=_COLOR_TEXT_SECONDARY,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        "点击右上角「添加监控路径」按钮开始配置",
                        size=13,
                        color=_COLOR_TEXT_SECONDARY,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            padding=40,
            alignment=ft.alignment.center,
        )

    # ------------------------------------------------------------------
    # 配置卡片
    # ------------------------------------------------------------------

    def _build_config_card(self, cfg: dict) -> ft.Container:
        """为单个扫描配置构建信息卡片。"""
        config_id = cfg["id"]
        exclude_patterns = cfg.get("exclude_patterns", "[]")
        if isinstance(exclude_patterns, str):
            try:
                patterns = json.loads(exclude_patterns)
            except (json.JSONDecodeError, TypeError):
                patterns = []
        else:
            patterns = exclude_patterns or []

        schedule_type = cfg.get("schedule_type", "manual")
        schedule_value = cfg.get("schedule_value", "")
        schedule_label = self._format_schedule_label(schedule_type, schedule_value)

        # 最后扫描时间
        latest = self.db.get_latest_snapshot(config_id)
        last_scan = format_datetime(latest["created_at"]) if latest else "从未扫描"

        # 排除规则展示
        exclude_text = ", ".join(patterns) if patterns else "无"

        # 进度条
        progress_bar = ft.ProgressBar(
            width=300,
            height=6,
            color=_COLOR_PRIMARY,
            bgcolor=_COLOR_BORDER,
            visible=False,
        )
        self._progress_bars[config_id] = progress_bar

        # 状态文字
        status_text = ft.Text("", size=12, color=_COLOR_TEXT_SECONDARY, visible=False)
        self._status_texts[config_id] = status_text

        # 结果摘要区域
        result_container = ft.Container(visible=False)
        self._result_bars[config_id] = result_container

        # 基准快照选择器
        baseline_options = [ft.dropdown.Option("latest", "最近一条快照（默认）")]
        hist_snaps = self.db.execute_query(
            "SELECT id, created_at, file_count FROM snapshots WHERE config_id = ? ORDER BY id DESC LIMIT 20",
            (config_id,),
        )
        for hs in hist_snaps:
            label = f"#{hs['id']}  {format_datetime(hs['created_at'])}  ({format_number(hs['file_count'])} 文件)"
            baseline_options.append(ft.dropdown.Option(str(hs["id"]), label))

        baseline_dropdown = ft.Dropdown(
            label="对比基准",
            options=baseline_options,
            value="latest",
            width=420,
            text_size=12,
            dense=True,
            visible=len(hist_snaps) > 0,
        )
        self._baseline_dropdowns[config_id] = baseline_dropdown

        card = ft.Container(
            content=ft.Column(
                controls=[
                    # 第一行：路径 + 操作按钮
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.FOLDER, color=_COLOR_PRIMARY, size=20),
                            ft.Text(
                                cfg["path"],
                                size=15,
                                weight=ft.FontWeight.W_600,
                                color=_COLOR_TEXT,
                                expand=True,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.OutlinedButton(
                                text="立即扫描",
                                icon=ft.Icons.PLAY_ARROW,
                                style=ft.ButtonStyle(
                                    color=_COLOR_PRIMARY,
                                    padding=ft.padding.symmetric(horizontal=10, vertical=4),
                                ),
                                on_click=lambda e, cid=config_id: self._on_scan_click(cid),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.EDIT_OUTLINED,
                                icon_color=_COLOR_TEXT_SECONDARY,
                                icon_size=20,
                                tooltip="编辑",
                                on_click=lambda e, cid=config_id: self._on_edit_click(cid),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_color=_COLOR_DANGER,
                                icon_size=20,
                                tooltip="删除",
                                on_click=lambda e, cid=config_id: self._on_delete_click(cid),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    # 第二行：详情标签
                    ft.Row(
                        controls=[
                            self._build_info_chip(ft.Icons.TIMER_OUTLINED, f"调度: {schedule_label}"),
                            self._build_info_chip(ft.Icons.ACCESS_TIME, f"上次扫描: {last_scan}"),
                            self._build_info_chip(ft.Icons.FILTER_LIST, f"排除: {exclude_text}"),
                        ],
                        wrap=True,
                        spacing=8,
                        run_spacing=4,
                    ),
                    # 基准快照选择器
                    baseline_dropdown,
                    # 进度条
                    ft.Row(
                        controls=[progress_bar, status_text],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    # 结果摘要
                    result_container,
                ],
                spacing=6,
            ),
            bgcolor=_COLOR_CARD,
            border_radius=8,
            padding=ft.padding.all(16),
            border=ft.border.all(1, _COLOR_BORDER),
        )
        return card

    def _build_info_chip(self, icon: str, text: str) -> ft.Container:
        """构建一个小标签，显示图标+文字。"""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(icon, size=14, color=_COLOR_TEXT_SECONDARY),
                    ft.Text(text, size=12, color=_COLOR_TEXT_SECONDARY),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=_COLOR_BG,
            border_radius=12,
            padding=ft.padding.symmetric(horizontal=10, vertical=4),
        )

    # ------------------------------------------------------------------
    # 调度标签格式化
    # ------------------------------------------------------------------

    @staticmethod
    def _format_schedule_label(schedule_type: str, schedule_value: str) -> str:
        """将调度类型和值格式化为可读的标签文字。"""
        if schedule_type == "manual":
            return "手动"
        elif schedule_type == "interval":
            try:
                minutes = int(schedule_value)
                if minutes >= 60:
                    hours = minutes // 60
                    mins = minutes % 60
                    return f"每{hours}小时" + (f"{mins}分钟" if mins else "")
                return f"每{minutes}分钟"
            except (ValueError, TypeError):
                return f"间隔: {schedule_value}"
        elif schedule_type == "daily":
            return f"每天 {schedule_value}"
        elif schedule_type == "weekly":
            return f"每周 {schedule_value}"
        else:
            return schedule_type

    # ------------------------------------------------------------------
    # 添加路径对话框
    # ------------------------------------------------------------------

    def _on_add_click(self, e):
        """点击「添加监控路径」按钮，弹出添加对话框。"""
        self._show_config_dialog(edit_mode=False, config_id=None, defaults=None)

    # ------------------------------------------------------------------
    # 编辑路径对话框
    # ------------------------------------------------------------------

    def _on_edit_click(self, config_id: int):
        """点击编辑按钮，弹出编辑对话框。"""
        configs = self.db.get_scan_configs()
        cfg = next((c for c in configs if c["id"] == config_id), None)
        if not cfg:
            return
        self._show_config_dialog(edit_mode=True, config_id=config_id, defaults=cfg)

    # ------------------------------------------------------------------
    # 通用配置对话框
    # ------------------------------------------------------------------

    def _show_config_dialog(self, edit_mode: bool, config_id: int | None, defaults: dict | None):
        """显示添加/编辑配置的对话框。"""
        defaults = defaults or {}

        # 路径输入
        path_field = ft.TextField(
            label="监控路径",
            value=defaults.get("path", ""),
            hint_text="例如: C:\\Users\\Documents",
            width=450,
            autofocus=True,
            prefix_icon=ft.Icons.FOLDER_OPEN,
        )

        def _on_pick_dir(e):
            def _handle_result(result: ft.FilePickerResultEvent):
                if result.path:
                    path_field.value = result.path
                    path_field.update()
            picker = ft.FilePicker(on_result=_handle_result)
            self.page.overlay.append(picker)
            self.page.update()
            picker.get_directory_path(dialog_title="选择监控目录")

        # 排除规则
        exclude_field = ft.TextField(
            label="排除规则",
            value=self._patterns_to_str(defaults.get("exclude_patterns", "[]")),
            hint_text="*.tmp, *.log, node_modules",
            width=450,
            prefix_icon=ft.Icons.FILTER_LIST,
        )

        # 调度类型
        schedule_type_dropdown = ft.Dropdown(
            label="调度类型",
            width=200,
            options=[
                ft.dropdown.Option("manual", "手动"),
                ft.dropdown.Option("interval", "按间隔"),
                ft.dropdown.Option("daily", "每天定时"),
                ft.dropdown.Option("weekly", "每周定时"),
            ],
            value=defaults.get("schedule_type", "manual"),
        )

        # 调度值容器（动态显示）
        schedule_value_field = ft.TextField(
            label="间隔（分钟）",
            width=200,
            value="",
            visible=False,
            keyboard_type=ft.KeyboardType.NUMBER,
            hint_text="例如: 60",
        )

        daily_time_field = ft.TextField(
            label="执行时间 (HH:MM)",
            width=200,
            value="",
            visible=False,
            hint_text="例如: 08:00",
        )

        weekly_field = ft.TextField(
            label="星期和时间",
            width=200,
            value="",
            visible=False,
            hint_text="例如: Mon 08:00",
        )

        schedule_value_container = ft.Column(
            controls=[schedule_value_field, daily_time_field, weekly_field],
            spacing=8,
        )

        # 预填调度值
        st = defaults.get("schedule_type", "manual")
        sv = defaults.get("schedule_value", "")
        if st == "interval":
            schedule_value_field.value = sv
            schedule_value_field.visible = True
        elif st == "daily":
            daily_time_field.value = sv
            daily_time_field.visible = True
        elif st == "weekly":
            weekly_field.value = sv
            weekly_field.visible = True

        def _on_schedule_type_change(e):
            val = schedule_type_dropdown.value
            schedule_value_field.visible = val == "interval"
            daily_time_field.visible = val == "daily"
            weekly_field.visible = val == "weekly"
            schedule_type_dropdown.update()
            schedule_value_container.update()

        schedule_type_dropdown.on_change = _on_schedule_type_change

        # 标题
        title = "编辑监控路径" if edit_mode else "添加监控路径"
        icon = ft.Icons.EDIT_NOTE if edit_mode else ft.Icons.ADD_CIRCLE

        # 保存回调
        def _on_save(e):
            path = path_field.value.strip()
            if not path:
                path_field.error_text = "请输入监控路径"
                path_field.update()
                return
            path_field.error_text = None
            path_field.update()

            exclude_str = exclude_field.value.strip()
            exclude_patterns = [p.strip() for p in exclude_str.split(",") if p.strip()] if exclude_str else []

            st_val = schedule_type_dropdown.value or "manual"
            sv_val = ""
            if st_val == "interval":
                sv_val = schedule_value_field.value.strip()
                if not sv_val:
                    schedule_value_field.error_text = "请输入间隔分钟数"
                    schedule_value_field.update()
                    return
            elif st_val == "daily":
                sv_val = daily_time_field.value.strip()
                if not sv_val:
                    daily_time_field.error_text = "请输入执行时间"
                    daily_time_field.update()
                    return
            elif st_val == "weekly":
                sv_val = weekly_field.value.strip()
                if not sv_val:
                    weekly_field.error_text = "请输入星期和时间"
                    weekly_field.update()
                    return

            if edit_mode and config_id is not None:
                self.db.update_scan_config(
                    config_id=config_id,
                    path=path,
                    exclude_patterns=exclude_patterns,
                    schedule_type=st_val,
                    schedule_value=sv_val,
                )
            else:
                new_id = self.db.add_scan_config(
                    path=path,
                    exclude_patterns=exclude_patterns,
                    schedule_type=st_val,
                    schedule_value=sv_val,
                )
                config_id = new_id

            # 同步到调度器 —— 创建/更新/删除定时任务
            try:
                if st_val in ("interval", "daily", "weekly"):
                    if not self.scheduler.is_running():
                        self.scheduler.start()
                    self.scheduler.add_job(config_id, st_val, sv_val)
                else:
                    self.scheduler.remove_job(config_id)
            except Exception as ex:
                # 不影响主流程，只提示
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"调度任务注册失败: {ex}"),
                    bgcolor="#ea4335",
                )
                self.page.snack_bar.open = True

            dialog.open = False
            self.page.update()
            self.refresh()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Icon(icon, color=_COLOR_PRIMARY, size=24),
                    ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
                ],
                spacing=8,
            ),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[path_field, ft.IconButton(
                            icon=ft.Icons.FOLDER_OPEN,
                            icon_color=_COLOR_PRIMARY,
                            tooltip="浏览",
                            on_click=_on_pick_dir,
                        )],
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    exclude_field,
                    schedule_type_dropdown,
                    schedule_value_container,
                ],
                spacing=16,
                width=500,
                tight=True,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: _close_dialog()),
                ft.ElevatedButton(
                    "保存",
                    icon=ft.Icons.SAVE,
                    style=ft.ButtonStyle(bgcolor=_COLOR_PRIMARY, color=ft.Colors.WHITE),
                    on_click=_on_save,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        def _close_dialog():
            dialog.open = False
            self.page.update()

        self.page.dialog = dialog  # type: ignore[attr-defined]
        dialog.open = True
        self.page.update()

    # ------------------------------------------------------------------
    # 删除配置
    # ------------------------------------------------------------------

    def _on_delete_click(self, config_id: int):
        """点击删除按钮，弹出确认对话框。"""
        def _confirm(e):
            try:
                self.scheduler.remove_job(config_id)  # 先移除调度任务
            except Exception:
                pass
            self.db.delete_scan_config(config_id)
            confirm_dialog.open = False
            self.page.update()
            self.refresh()

        def _cancel(e):
            confirm_dialog.open = False
            self.page.update()

        confirm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=_COLOR_DANGER, size=24),
                    ft.Text("确认删除", size=18, weight=ft.FontWeight.BOLD),
                ],
                spacing=8,
            ),
            content=ft.Text("确定要删除此监控路径吗？相关的历史快照数据将被保留。"),
            actions=[
                ft.TextButton("取消", on_click=_cancel),
                ft.ElevatedButton(
                    "删除",
                    icon=ft.Icons.DELETE,
                    style=ft.ButtonStyle(bgcolor=_COLOR_DANGER, color=ft.Colors.WHITE),
                    on_click=_confirm,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.dialog = confirm_dialog  # type: ignore[attr-defined]
        confirm_dialog.open = True
        self.page.update()

    # ------------------------------------------------------------------
    # 立即扫描
    # ------------------------------------------------------------------

    def _on_scan_click(self, config_id: int):
        """点击「立即扫描」，启动后台扫描线程。"""
        progress_bar = self._progress_bars.get(config_id)
        status_text = self._status_texts.get(config_id)
        result_container = self._result_bars.get(config_id)
        baseline_dd = self._baseline_dropdowns.get(config_id)

        if progress_bar is None or status_text is None:
            return

        # 读取基准快照选择
        baseline_snapshot_id = None
        if baseline_dd and baseline_dd.value and baseline_dd.value != "latest":
            try:
                baseline_snapshot_id = int(baseline_dd.value)
            except (ValueError, TypeError):
                baseline_snapshot_id = None

        baseline_label = f"#{baseline_snapshot_id}" if baseline_snapshot_id else "最近一条快照"

        # 显示进度条
        progress_bar.visible = True
        progress_bar.value = None  # 不确定模式
        status_text.value = f"正在扫描...（对比基准: {baseline_label}）"
        status_text.visible = True
        if result_container:
            result_container.visible = False
        self.page.update()

        def _run_scan():
            try:
                # 进度回调
                def _progress_cb(file_count: int, dir_count: int):
                    status_text.value = f"正在扫描... 已发现 {format_number(file_count)} 个文件, {format_number(dir_count)} 个目录"
                    try:
                        self.page.update()
                    except Exception:
                        pass

                result = self.snapshot_engine.run_scan(config_id, baseline_snapshot_id)

                # 扫描完成
                baseline_id = result.get("baseline_snapshot_id")
                bl = f"（基准: #{baseline_id}）" if baseline_id else "（首次扫描，无对比）"
                progress_bar.value = 1.0
                status_text.value = f"扫描完成 · 耗时 {format_duration(result.get('duration', 0))} {bl}"
                status_text.color = _COLOR_SUCCESS
                self.page.update()

                # 显示结果摘要
                comparison = result.get("comparison")
                if comparison and result_container:
                    summary = comparison.get("summary", {})
                    changes = {
                        "added": comparison.get("added", []),
                        "removed": comparison.get("removed", []),
                        "modified": comparison.get("modified", []),
                    }
                    result_container.content = self._build_scan_result(summary, changes)
                    result_container.visible = True

                self.page.update()

            except Exception as exc:
                progress_bar.value = 0
                status_text.value = f"扫描失败: {exc}"
                status_text.color = _COLOR_DANGER
                self.page.update()

        thread = threading.Thread(target=_run_scan, daemon=True)
        thread.start()

    def _build_scan_result(self, summary: dict, changes: dict = None) -> ft.Container:
        """构建扫描结果摘要区域，包含统计和文件列表。"""
        added = summary.get("added_count", 0)
        removed = summary.get("removed_count", 0)
        modified = summary.get("modified_count", 0)
        size_delta = summary.get("size_delta", 0)

        delta_color = _COLOR_SUCCESS if size_delta >= 0 else _COLOR_DANGER
        delta_sign = "+" if size_delta >= 0 else ""
        delta_text = f"{delta_sign}{format_size(abs(size_delta))}"

        # 统计数字行
        stats_row = ft.Row(
            controls=[
                self._build_stat_chip(ft.Icons.ADD_CIRCLE, f"新增: {format_number(added)}", _COLOR_SUCCESS),
                self._build_stat_chip(ft.Icons.REMOVE_CIRCLE, f"删除: {format_number(removed)}", _COLOR_DANGER),
                self._build_stat_chip(ft.Icons.EDIT, f"修改: {format_number(modified)}", _COLOR_WARNING),
                self._build_stat_chip(ft.Icons.STORAGE, f"容量变化: {delta_text}", delta_color),
            ],
            spacing=12,
            wrap=True,
        )

        # 具体文件列表
        file_list_controls = []
        if changes:
            max_show = 50  # 每类最多显示 50 条

            if changes.get("added"):
                file_list_controls.append(
                    self._build_file_section("新增文件", _COLOR_SUCCESS, changes["added"], max_show)
                )
            if changes.get("removed"):
                file_list_controls.append(
                    self._build_file_section("删除文件", _COLOR_DANGER, changes["removed"], max_show)
                )
            if changes.get("modified"):
                file_list_controls.append(
                    self._build_file_section("修改文件", _COLOR_WARNING, changes["modified"], max_show)
                )

        content_controls = [stats_row]
        if file_list_controls:
            content_controls.append(ft.Divider(height=1, color=_COLOR_BORDER))
            content_controls.extend(file_list_controls)

        return ft.Container(
            content=ft.Column(
                controls=content_controls,
                spacing=6,
            ),
            padding=ft.padding.only(left=0, top=8, right=0, bottom=0),
        )

    def _build_file_section(self, title: str, color: str, items: list, max_show: int) -> ft.Column:
        """构建某一类变化（新增/删除/修改）的文件列表区块。"""
        file_rows = []
        shown = items[:max_show]
        for item in shown:
            path = item.get("path", "")
            size = item.get("size", 0)
            old_size = item.get("old_size", 0)

            # 缩短路径显示
            display_path = path
            if len(display_path) > 80:
                display_path = "..." + display_path[-77:]

            size_text = format_size(size) if size else ""
            if old_size and title == "修改文件":
                size_text = f"{format_size(old_size)} → {format_size(size)}"

            file_rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Container(width=4, height=4, bgcolor=color, border_radius=2),
                            ft.Text(
                                display_path,
                                size=11,
                                color=_COLOR_TEXT,
                                expand=True,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                tooltip=path,
                            ),
                            ft.Text(size_text, size=11, color=_COLOR_TEXT_SECONDARY),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.padding.only(left=12, top=2, right=8, bottom=2),
                )
            )

        # 如果有更多，显示提示
        remaining = len(items) - max_show
        if remaining > 0:
            file_rows.append(
                ft.Container(
                    content=ft.Text(
                        f"... 还有 {format_number(remaining)} 个文件未显示，请在「历史记录」中查看完整列表",
                        size=11,
                        color=_COLOR_TEXT_SECONDARY,
                        italic=True,
                    ),
                    padding=ft.padding.only(left=16, top=4, bottom=4),
                )
            )

        return ft.Column(
            controls=[
                ft.Text(title, size=13, weight=ft.FontWeight.W_600, color=color),
                *file_rows,
            ],
            spacing=2,
        )

    def _build_stat_chip(self, icon: str, text: str, color: str) -> ft.Container:
        """构建一个统计数据小标签。"""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(icon, size=16, color=color),
                    ft.Text(text, size=12, weight=ft.FontWeight.W_600, color=color),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=f"{color}18",
            border_radius=12,
            padding=ft.padding.symmetric(horizontal=10, vertical=4),
        )

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _patterns_to_str(patterns) -> str:
        """将排除规则列表/JSON 字符串转为逗号分隔的字符串。"""
        if isinstance(patterns, str):
            try:
                patterns = json.loads(patterns)
            except (json.JSONDecodeError, TypeError):
                return patterns
        if isinstance(patterns, list):
            return ", ".join(patterns)
        return ""
