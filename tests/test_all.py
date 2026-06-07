"""
DiskSentinel 完整自动化测试套件
覆盖所有核心模块的功能路径
"""
import sys
import os
import tempfile
import shutil
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

# ============================================================================
# 测试框架
# ============================================================================
passed = 0
failed = 0
errors = []

def test(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"  ✅ {name}")
    except Exception as e:
        failed += 1
        errors.append((name, str(e)))
        print(f"  ❌ {name}: {e}")

def assert_eq(a, b):
    if a != b:
        raise AssertionError(f"'{a}' != '{b}'")

def assert_true(cond):
    if not cond:
        raise AssertionError(f"Expected True, got False")


# ============================================================================
# 准备：干净的数据库 + 测试目录
# ============================================================================
DB_PATH = os.path.expanduser("~/.disksentinel/data.db")
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

TEST_DIR = os.path.join(tempfile.gettempdir(), "disksentinel_test")
if os.path.exists(TEST_DIR):
    shutil.rmtree(TEST_DIR)
os.makedirs(TEST_DIR)

# 创建测试文件
os.makedirs(os.path.join(TEST_DIR, "subdir1"), exist_ok=True)
os.makedirs(os.path.join(TEST_DIR, "subdir2"), exist_ok=True)

with open(os.path.join(TEST_DIR, "file1.txt"), "w") as f:
    f.write("A" * 1000)  # 1000 bytes
with open(os.path.join(TEST_DIR, "file2.log"), "w") as f:
    f.write("B" * 2000)  # 2000 bytes
with open(os.path.join(TEST_DIR, "subdir1", "file3.txt"), "w") as f:
    f.write("C" * 3000)  # 3000 bytes
with open(os.path.join(TEST_DIR, "subdir1", "file4.tmp"), "w") as f:
    f.write("D" * 500)   # 500 bytes (应被排除)
with open(os.path.join(TEST_DIR, "subdir2", "file5.py"), "w") as f:
    f.write("E" * 1500)  # 1500 bytes

print("=" * 60)
print("DiskSentinel 自动化测试")
print("=" * 60)

# ============================================================================
# 1. 格式化工具测试
# ============================================================================
print("\n[1] 格式化工具 (format.py)")
from src.utils.format import format_size, format_number, format_datetime, format_duration

test("format_size(0) == '0 B'", lambda: assert_eq(format_size(0), "0 B"))
test("format_size(512) 包含 512", lambda: assert_true('512' in format_size(512)))
test("format_size(1024) == '1.0 KB'", lambda: assert_eq(format_size(1024), "1.0 KB"))
test("format_size(1536) == '1.5 KB'", lambda: assert_eq(format_size(1536), "1.5 KB"))
test("format_size(1048576) == '1.0 MB'", lambda: assert_eq(format_size(1048576), "1.0 MB"))
test("format_size(1073741824) == '1.0 GB'", lambda: assert_eq(format_size(1073741824), "1.0 GB"))
test("format_number(0) == '0'", lambda: assert_eq(format_number(0), "0"))
test("format_number(1234) == '1,234'", lambda: assert_eq(format_number(1234), "1,234"))
test("format_number(1234567) == '1,234,567'", lambda: assert_eq(format_number(1234567), "1,234,567"))
test("format_duration(0) == '0秒'", lambda: assert_eq(format_duration(0), "0秒"))
test("format_duration(30) == '30秒'", lambda: assert_eq(format_duration(30), "30秒"))
test("format_duration(90) == '1分30秒'", lambda: assert_eq(format_duration(90), "1分30秒"))
test("format_duration(3661) == '1小时1分1秒'", lambda: assert_eq(format_duration(3661), "1小时1分1秒"))

# ============================================================================
# 2. 平台工具测试
# ============================================================================
print("\n[2] 平台工具 (platform_utils.py)")
from src.utils.platform_utils import get_system_drives, get_home_directory, get_data_directory

test("get_system_drives() 非空", lambda: assert_true(len(get_system_drives()) > 0))
test("get_home_directory() 非空", lambda: assert_true(bool(get_home_directory())))
test("get_data_directory() 包含 disksentinel", lambda: assert_true("disksentinel" in get_data_directory()))


# ============================================================================
# 3. 数据库模块测试
# ============================================================================
print("\n[3] 数据库模块 (database.py)")
from src.core.database import DatabaseManager

db = DatabaseManager()

test("init_db() 创建所有表", lambda: db.init_db())

test("add_scan_config()", lambda: assert_true(db.add_scan_config("/tmp", "*.tmp", "manual", "") > 0))

config_id = db.add_scan_config(TEST_DIR, "*.tmp, *.log", "interval", "60")

test("get_scan_configs() 返回配置", lambda: assert_true(len(db.get_scan_configs()) >= 2))

configs = db.get_scan_configs()
test_cfg = [c for c in configs if c["path"] == TEST_DIR][0]

test("update_scan_config()", lambda: db.update_scan_config(
    test_cfg["id"], TEST_DIR, "*.tmp", "daily", "08:00"
))

test("create_snapshot()", lambda: assert_true(
    db.create_snapshot(config_id=test_cfg["id"], file_count=10, total_size=5000, duration=1.5) > 0
))

snap_id = db.create_snapshot(config_id=test_cfg["id"], file_count=12, total_size=8000, duration=2.3)

test("add_file_entry()", lambda: db.add_file_entry(snap_id, "/test/a.txt", 100, "2026-01-01", False))

test("add_file_entries_bulk()", lambda: db.add_file_entries_bulk([
    (snap_id, "/test/b.txt", 200, "2026-01-01", False),
    (snap_id, "/test/c.txt", 300, "2026-01-01", False),
]))

test("add_change()", lambda: db.add_change(snap_id, "added", "/test/new.txt", 500, 0))

test("add_changes_bulk()", lambda: db.add_changes_bulk([
    (snap_id, "removed", "/test/old.txt", 0, 400),
    (snap_id, "modified", "/test/mod.txt", 600, 300),
]))

changes = db.get_changes_for_snapshot(snap_id)
test("get_changes_for_snapshot() 返回 3 条", lambda: assert_eq(len(changes), 3))

test("get_snapshots()", lambda: assert_true(len(db.get_snapshots(limit=5)) >= 1))

test("get_latest_snapshot()", lambda: assert_true(db.get_latest_snapshot(test_cfg["id"]) is not None))

test("add_watch_event()", lambda: db.add_watch_event(test_cfg["id"], "created", "/test/watch.txt", "", 100))

events = db.get_watch_events(limit=10)
test("get_watch_events()", lambda: assert_true(len(events) >= 1))

test("get_dashboard_stats()", lambda: assert_true(isinstance(db.get_dashboard_stats(), dict)))

stats = db.get_dashboard_stats()
test("stats 含必要字段", lambda: assert_true(all(k in stats for k in [
    "total_configs", "total_snapshots", "total_files", "total_size",
    "changes_today", "watch_events_today", "last_scan_time"
])))

# execute_query / fetch_one / fetch_all
test("execute_query()", lambda: assert_true(len(db.execute_query("SELECT 1 as val")) == 1))
test("fetch_one()", lambda: assert_true(db.fetch_one("SELECT 1 as val")["val"] == 1))
test("fetch_all()", lambda: assert_true(len(db.fetch_all("SELECT 1 as val")) == 1))
test("execute_insert()", lambda: assert_true(db.execute_insert(
    "INSERT INTO watch_events (config_id, event_type, src_path, size) VALUES (?, 'test', '/x', 0)",
    (test_cfg["id"],)
) > 0))

# ============================================================================
# 4. 快照引擎测试
# ============================================================================
print("\n[4] 快照引擎 (snapshot.py)")
from src.core.snapshot import SnapshotEngine

# 清理旧测试数据，重新来
db.close()
time.sleep(0.5)
os.remove(DB_PATH)
db2 = DatabaseManager()
db2.init_db()
engine = SnapshotEngine(db2)

cid = db2.add_scan_config(TEST_DIR, "*.tmp, *.log", "manual", "")

test("首次扫描", lambda: assert_true(engine.scan_path(TEST_DIR, "*.tmp, *.log", cid) > 0))

snap1 = engine.scan_path(TEST_DIR, "*.tmp, *.log", cid)

# 修改文件：新增、删除、修改
with open(os.path.join(TEST_DIR, "new_file.txt"), "w") as f:
    f.write("NEW" * 500)
os.remove(os.path.join(TEST_DIR, "file1.txt"))  # 删除 .txt 文件（不被排除）
with open(os.path.join(TEST_DIR, "subdir2", "file5.py"), "w") as f:
    f.write("MODIFIED" * 3000)

snap2 = engine.scan_path(TEST_DIR, "*.tmp, *.log", cid)

test("对比扫描 (compare_snapshots)", lambda: assert_true(
    isinstance(engine.compare_snapshots(snap1, snap2), dict)
))

comparison = engine.compare_snapshots(snap1, snap2)
test("检测到新增文件", lambda: assert_true(comparison["summary"]["added_count"] >= 1))
test("检测到删除文件", lambda: assert_true(comparison["summary"]["removed_count"] >= 1))
test("检测到修改文件", lambda: assert_true(comparison["summary"]["modified_count"] >= 1))
test("新增大小 > 0", lambda: assert_true(comparison["summary"]["added_size"] > 0))
test("删除大小 > 0", lambda: assert_true(comparison["summary"]["removed_size"] > 0))

test("run_scan() 完整流程", lambda: assert_true(isinstance(engine.run_scan(cid), dict)))

run_result = engine.run_scan(cid)
test("run_scan 返回 snapshot_id", lambda: assert_true(run_result["snapshot_id"] > 0))
test("run_scan 返回 file_count", lambda: assert_true(run_result["file_count"] >= 0))
test("run_scan 返回 total_size", lambda: assert_true(run_result["total_size"] >= 0))
test("run_scan 返回 duration", lambda: assert_true(run_result["duration"] >= 0))

# ============================================================================
# 5. 实时监控测试
# ============================================================================
print("\n[5] 实时监控 (watcher.py)")
from src.core.watcher import FileWatcher

watcher = FileWatcher(db2)

test("FileWatcher 创建", lambda: assert_true(watcher is not None))

test("start_watching()", lambda: watcher.start_watching([TEST_DIR], cid))
time.sleep(2)

# 触发文件事件
with open(os.path.join(TEST_DIR, "watch_test.txt"), "w") as f:
    f.write("watch test")

time.sleep(3)

events = watcher.get_recent_events(limit=10)
test("监控到文件事件", lambda: assert_true(len(events) >= 1))

test("stop_watching()", lambda: watcher.stop_watching())

# ============================================================================
# 6. 定时调度器测试
# ============================================================================
print("\n[6] 定时调度器 (scheduler.py)")
from src.core.scheduler import ScanScheduler

sched = ScanScheduler(db2, engine)

test("ScanScheduler 创建", lambda: assert_true(sched is not None))

test("scheduler.start()", lambda: sched.start())

test("scheduler.add_job(interval)", lambda: sched.add_job(cid, "interval", "999999"))

test("scheduler.get_next_run_time()", lambda: assert_true(sched.get_next_run_time(cid) is not None))

test("scheduler.remove_job()", lambda: sched.remove_job(cid))

test("scheduler.stop()", lambda: sched.stop())

# ============================================================================
# 7. 报表生成测试
# ============================================================================
print("\n[7] 报表生成 (reporter.py)")
from src.core.reporter import ReportGenerator

reporter = ReportGenerator(db2)
out_dir = os.path.join(tempfile.gettempdir(), "ds_reports")
os.makedirs(out_dir, exist_ok=True)

test("generate_summary()", lambda: assert_true(isinstance(reporter.generate_summary(snap2), dict)))

test("generate_csv()", lambda: reporter.generate_csv(snap2, os.path.join(out_dir, "report.csv")))
csv_path = os.path.join(out_dir, "report.csv")
test("CSV 文件存在", lambda: assert_true(os.path.exists(csv_path)))
test("CSV 非空", lambda: assert_true(os.path.getsize(csv_path) > 0))

test("generate_html()", lambda: reporter.generate_html(snap2, os.path.join(out_dir, "report.html")))
html_path = os.path.join(out_dir, "report.html")
test("HTML 文件存在", lambda: assert_true(os.path.exists(html_path)))
test("HTML 非空", lambda: assert_true(os.path.getsize(html_path) > 0))

# ============================================================================
# 8. UI 模块导入 + 构建（无头测试）
# ============================================================================
print("\n[8] UI 模块导入测试")
test("DashboardPage 导入", lambda: __import__("src.ui.dashboard", fromlist=["DashboardPage"]))
test("ScannerPage 导入", lambda: __import__("src.ui.scanner", fromlist=["ScannerPage"]))
test("MonitorPage 导入", lambda: __import__("src.ui.monitor", fromlist=["MonitorPage"]))
test("HistoryPage 导入", lambda: __import__("src.ui.history", fromlist=["HistoryPage"]))
test("SettingsPage 导入", lambda: __import__("src.ui.settings", fromlist=["SettingsPage"]))

# ============================================================================
# 9. 清理旧数据测试
# ============================================================================
print("\n[9] 数据清理 (cleanup_old_data)")
test("cleanup_old_data()", lambda: assert_true(isinstance(db2.cleanup_old_data(90), dict)))

# ============================================================================
# 结果
# ============================================================================
print("\n" + "=" * 60)
print(f"测试结果: ✅ {passed} 通过, ❌ {failed} 失败")
print("=" * 60)

if errors:
    print("\n失败详情:")
    for name, err in errors:
        print(f"  ❌ {name}: {err}")

# 清理测试文件
shutil.rmtree(TEST_DIR, ignore_errors=True)
shutil.rmtree(out_dir, ignore_errors=True)
try:
    db2.close()
except:
    pass
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

sys.exit(0 if failed == 0 else 1)
