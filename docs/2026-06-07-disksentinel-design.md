# DiskSentinel — 磁盘文件变化监控工具 设计文档

> **日期**: 2026-06-07
> **状态**: 已批准

## 1. 项目概述

DiskSentinel 是一款跨平台（Windows / Linux / macOS）桌面应用，用于监控文件系统变化——检测新增、删除、修改的文件及对应容量变化。支持手动触发和定时触发两种模式，可选实时监控。

## 2. 目标用户

普通用户（非技术人员），需要友好的图形界面。

## 3. 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| GUI | Flet (Python + Flutter) | 原生渲染，三平台打包简单 |
| 文件扫描 | os.walk + pathlib | 跨平台文件遍历 |
| 实时监控 | watchdog | 跨平台文件系统事件监控 |
| 数据存储 | SQLite | 本地嵌入式数据库 |
| 定时任务 | APScheduler | 灵活的定时调度 |
| 图表 | Flet 内置图表 | 趋势图展示 |
| 报表导出 | CSV / HTML | 变化报告 |
| 打包 | PyInstaller / flet build | 三平台安装包 |

## 4. 功能模块

### 4.1 仪表盘
- 显示当前监控路径状态
- 统计概览：总文件数、总大小、新增/删除数量
- 容量变化趋势图

### 4.2 快照扫描
- 手动触发：点击按钮立即扫描
- 定时触发：配置 cron 表达式或简单间隔
- 扫描指定目录/磁盘，生成快照
- 与上次快照对比，生成变化报告

### 4.3 实时监控
- 可选开关：启用/禁用
- 使用 watchdog 监控指定路径
- 实时显示文件增删改事件
- 事件日志记录

### 4.4 历史记录
- 查看所有历史扫描记录
- 按时间范围筛选
- 查看每次扫描的详细变化

### 4.5 设置
- 监控路径配置（多路径）
- 排除规则（按扩展名、目录名）
- 定时扫描计划
- 实时监控开关
- 数据保留策略

## 5. 数据模型

```sql
-- 扫描配置
CREATE TABLE scan_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    exclude_patterns TEXT DEFAULT '',
    schedule_type TEXT DEFAULT 'manual',  -- manual/interval/cron
    schedule_value TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 快照记录
CREATE TABLE snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id INTEGER REFERENCES scan_configs(id),
    scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_count INTEGER DEFAULT 0,
    total_size INTEGER DEFAULT 0,
    duration_seconds REAL DEFAULT 0
);

-- 文件条目（快照详情）
CREATE TABLE file_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER REFERENCES snapshots(id),
    path TEXT NOT NULL,
    size INTEGER DEFAULT 0,
    modified_time TIMESTAMP,
    is_dir INTEGER DEFAULT 0
);

-- 变化记录
CREATE TABLE changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER REFERENCES snapshots(id),
    change_type TEXT NOT NULL,  -- added/removed/modified
    path TEXT NOT NULL,
    size INTEGER DEFAULT 0,
    old_size INTEGER DEFAULT 0,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 实时监控事件
CREATE TABLE watch_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id INTEGER REFERENCES scan_configs(id),
    event_type TEXT NOT NULL,  -- created/deleted/modified/moved
    src_path TEXT NOT NULL,
    dest_path TEXT DEFAULT '',
    size INTEGER DEFAULT 0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 6. 项目结构

```
disk-sentinel/
├── src/
│   ├── main.py              # 应用入口
│   ├── app.py               # Flet 应用主体
│   ├── ui/                  # UI 组件
│   │   ├── __init__.py
│   │   ├── dashboard.py     # 仪表盘页面
│   │   ├── scanner.py       # 扫描管理页面
│   │   ├── monitor.py       # 实时监控页面
│   │   ├── history.py       # 历史记录页面
│   │   └── settings.py      # 设置页面
│   ├── core/                # 核心业务逻辑
│   │   ├── __init__.py
│   │   ├── snapshot.py      # 快照引擎（扫描+对比）
│   │   ├── watcher.py       # 实时文件监控
│   │   ├── database.py      # 数据库管理
│   │   ├── scheduler.py     # 定时任务管理
│   │   └── reporter.py      # 报表生成
│   └── utils/
│       ├── __init__.py
│       ├── format.py        # 格式化工具（大小、时间）
│       └── platform_utils.py # 平台相关工具
├── tests/
│   ├── test_snapshot.py
│   ├── test_database.py
│   └── test_watcher.py
├── requirements.txt
├── build.py                 # 打包脚本
└── README.md
```

## 7. 打包分发

- **Windows**: `.exe` 安装包 (PyInstaller + Inno Setup 或 NSIS)
- **macOS**: `.dmg` 安装包
- **Linux**: `.AppImage` + `.deb`

## 8. 非功能性需求

- 首次扫描 C 盘全量不应超过 5 分钟
- 快照数据库文件大小控制在合理范围（定期清理）
- UI 响应时间 < 200ms
- 实时监控 CPU 占用 < 5%
