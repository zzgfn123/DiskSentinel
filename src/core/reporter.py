"""
DiskSentinel - 报表生成模块

支持将快照对比结果导出为 CSV 和 HTML 报表，
并生成变化摘要统计。
"""

import csv
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


class ReportGenerator:
    """报表生成器，支持 CSV / HTML 导出及摘要统计。"""

    # HTML 报表内联样式
    _HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DiskSentinel 变化报表</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
    background: #f5f7fa; color: #333; padding: 24px;
  }}
  h1 {{
    font-size: 22px; margin-bottom: 6px; color: #1a73e8;
  }}
  .meta {{
    font-size: 13px; color: #888; margin-bottom: 20px;
  }}
  .summary {{
    display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap;
  }}
  .summary-card {{
    background: #fff; border-radius: 8px; padding: 16px 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); min-width: 140px;
  }}
  .summary-card .label {{ font-size: 12px; color: #888; margin-bottom: 4px; }}
  .summary-card .value {{ font-size: 24px; font-weight: 700; color: #1a73e8; }}
  .summary-card.added .value {{ color: #34a853; }}
  .summary-card.removed .value {{ color: #ea4335; }}
  .summary-card.modified .value {{ color: #fbbc04; }}
  .summary-card.total .value {{ color: #1a73e8; }}
  table {{
    width: 100%; border-collapse: collapse; background: #fff;
    border-radius: 8px; overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  th {{
    background: #1a73e8; color: #fff; text-align: left;
    padding: 12px 16px; font-size: 13px;
  }}
  td {{
    padding: 10px 16px; border-bottom: 1px solid #eee; font-size: 13px;
    word-break: break-all;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover {{ background: #f0f4ff; }}
  .badge {{
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 11px; font-weight: 600; color: #fff;
  }}
  .badge.added {{ background: #34a853; }}
  .badge.removed {{ background: #ea4335; }}
  .badge.modified {{ background: #fbbc04; color: #333; }}
  .footer {{
    margin-top: 24px; font-size: 12px; color: #aaa; text-align: center;
  }}
</style>
</head>
<body>
  <h1>DiskSentinel 变化报表</h1>
  <p class="meta">快照 ID: {snapshot_id} | 生成时间: {generated_at}</p>

  <div class="summary">
    <div class="summary-card added">
      <div class="label">新增文件</div>
      <div class="value">{added_count}</div>
    </div>
    <div class="summary-card removed">
      <div class="label">删除文件</div>
      <div class="value">{removed_count}</div>
    </div>
    <div class="summary-card modified">
      <div class="label">修改文件</div>
      <div class="value">{modified_count}</div>
    </div>
    <div class="summary-card total">
      <div class="label">变化总计</div>
      <div class="value">{total_count}</div>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>类型</th>
        <th>路径</th>
        <th>新大小</th>
        <th>旧大小</th>
        <th>检测时间</th>
      </tr>
    </thead>
    <tbody>
{rows_html}
    </tbody>
  </table>

  <p class="footer">由 DiskSentinel 自动生成</p>
</body>
</html>"""

    def __init__(self, db_manager):
        """
        初始化报表生成器。

        Args:
            db_manager: 数据库管理器实例 (DatabaseManager)
        """
        self.db_manager = db_manager

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def generate_csv(self, snapshot_id, output_path):
        """
        将指定快照的变化记录导出为 CSV 文件。

        Args:
            snapshot_id: 快照 ID (int)
            output_path: 输出文件路径 (str)，如 "report.csv"

        Returns:
            str: 生成的 CSV 文件绝对路径

        Raises:
            ValueError: 指定快照不存在或无变化记录
        """
        changes = self._fetch_changes(snapshot_id)
        if not changes:
            logger.warning("快照 %s 无变化记录，CSV 为空", snapshot_id)

        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["#", "类型", "路径", "新大小(字节)", "旧大小(字节)", "检测时间"])
            for idx, row in enumerate(changes, 1):
                writer.writerow([
                    idx,
                    row["change_type"],
                    row["path"],
                    row["size"],
                    row["old_size"],
                    row["created_at"],
                ])

        logger.info("CSV 报表已生成: %s (%d 条记录)", output_path, len(changes))
        return output_path

    def generate_html(self, snapshot_id, output_path):
        """
        将指定快照的变化记录导出为 HTML 文件。

        生成的 HTML 包含：
        - 摘要统计卡片（新增/删除/修改/总计）
        - 完整的变化记录表格
        - 内联 CSS 美化

        Args:
            snapshot_id: 快照 ID (int)
            output_path: 输出文件路径 (str)，如 "report.html"

        Returns:
            str: 生成的 HTML 文件绝对路径

        Raises:
            ValueError: 指定快照不存在
        """
        changes = self._fetch_changes(snapshot_id)
        summary = self.generate_summary(snapshot_id)

        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # 构建表格行
        rows_html_parts = []
        for idx, row in enumerate(changes, 1):
            change_type = row["change_type"]
            size_str = self._format_size(row["size"])
            old_size_str = self._format_size(row["old_size"])
            rows_html_parts.append(
                f'      <tr>'
                f'<td>{idx}</td>'
                f'<td><span class="badge {change_type}">{change_type}</span></td>'
                f'<td>{self._escape_html(row["path"])}</td>'
                f'<td>{size_str}</td>'
                f'<td>{old_size_str}</td>'
                f'<td>{row["created_at"]}</td>'
                f'</tr>'
            )
        rows_html = "\n".join(rows_html_parts)

        html_content = self._HTML_TEMPLATE.format(
            snapshot_id=snapshot_id,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            added_count=summary.get("added_count", 0),
            removed_count=summary.get("removed_count", 0),
            modified_count=summary.get("modified_count", 0),
            total_count=summary.get("total_count", 0),
            rows_html=rows_html,
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info("HTML 报表已生成: %s (%d 条记录)", output_path, len(changes))
        return output_path

    def generate_summary(self, snapshot_id):
        """
        生成指定快照的变化摘要统计。

        Args:
            snapshot_id: 快照 ID (int)

        Returns:
            dict: 包含以下字段:
                - snapshot_id (int)
                - added_count (int)
                - removed_count (int)
                - modified_count (int)
                - total_count (int)
                - total_added_size (int)   新增文件总大小
                - total_removed_size (int)  删除文件总大小
                - total_modified_size (int) 修改文件当前总大小
        """
        try:
            row = self.db_manager.fetch_one(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN change_type = 'added'   THEN 1 ELSE 0 END), 0) AS added_count,
                    COALESCE(SUM(CASE WHEN change_type = 'removed' THEN 1 ELSE 0 END), 0) AS removed_count,
                    COALESCE(SUM(CASE WHEN change_type = 'modified'THEN 1 ELSE 0 END), 0) AS modified_count,
                    COUNT(*) AS total_count,
                    COALESCE(SUM(CASE WHEN change_type = 'added'    THEN size ELSE 0 END), 0) AS total_added_size,
                    COALESCE(SUM(CASE WHEN change_type = 'removed'  THEN size ELSE 0 END), 0) AS total_removed_size,
                    COALESCE(SUM(CASE WHEN change_type = 'modified' THEN size ELSE 0 END), 0) AS total_modified_size
                FROM changes
                WHERE snapshot_id = ?
                """,
                (snapshot_id,),
            )
        except Exception as e:
            logger.error("获取摘要统计失败: %s", e)
            return {
                "snapshot_id": snapshot_id,
                "added_count": 0, "removed_count": 0,
                "modified_count": 0, "total_count": 0,
                "total_added_size": 0, "total_removed_size": 0,
                "total_modified_size": 0,
            }

        if row is None:
            added, removed, modified, total = 0, 0, 0, 0
            added_size, removed_size, modified_size = 0, 0, 0
        else:
            added, removed, modified, total = row["added_count"], row["removed_count"], row["modified_count"], row["total_count"]
            added_size, removed_size, modified_size = row["total_added_size"], row["total_removed_size"], row["total_modified_size"]

        return {
            "snapshot_id": snapshot_id,
            "added_count": added,
            "removed_count": removed,
            "modified_count": modified,
            "total_count": total,
            "total_added_size": added_size,
            "total_removed_size": removed_size,
            "total_modified_size": modified_size,
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _fetch_changes(self, snapshot_id):
        """
        从数据库获取指定快照的所有变化记录。

        Args:
            snapshot_id: 快照 ID

        Returns:
            list[dict]: 变化记录列表
        """
        try:
            rows = self.db_manager.fetch_all(
                """
                SELECT id, change_type, path, size, old_size, created_at
                FROM changes
                WHERE snapshot_id = ?
                ORDER BY created_at
                """,
                (snapshot_id,),
            )
            return [
                {
                    "id": r["id"],
                    "change_type": r["change_type"],
                    "path": r["path"],
                    "size": r["size"],
                    "old_size": r["old_size"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("获取变化记录失败: %s", e)
            return []

    @staticmethod
    def _format_size(size_bytes):
        """将字节数格式化为人类可读的字符串。"""
        if size_bytes is None or size_bytes == 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        for unit in units:
            if abs(size) < 1024.0 or unit == units[-1]:
                if unit == "B":
                    return f"{int(size)} B"
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size_bytes} B"

    @staticmethod
    def _escape_html(text):
        """转义 HTML 特殊字符。"""
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
