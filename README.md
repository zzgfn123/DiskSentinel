# DiskSentinel - 磁盘文件变化监控工具

🔍 一款跨平台桌面应用，用于监控文件系统的新增、删除、修改文件及对应容量变化。

## ✨ 功能特性

- **快照对比扫描** — 手动或定时扫描指定目录，对比两次快照发现文件变化
- **实时文件监控** — 可选开启 watchdog 实时监控文件增删改
- **容量变化统计** — 精确统计文件新增/减少带来的容量变化
- **可视化仪表盘** — 图表展示变化趋势，一目了然
- **报表导出** — 支持导出 CSV / HTML 格式的变化报告
- **跨平台支持** — Windows / Linux / macOS

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| GUI | Flet (Python + Flutter) |
| 实时监控 | Watchdog |
| 定时任务 | APScheduler |
| 数据存储 | SQLite |
| 打包 | PyInstaller |

## 📦 安装

### 从源码安装

```bash
# 克隆项目
git clone <repo-url>
cd disk-sentinel

# 安装依赖
pip install -r requirements.txt

# 启动应用
python main.py
```

### 打包为可安装客户端

```bash
# 安装 PyInstaller
pip install pyinstaller

# 执行打包
python build.py
```

打包完成后，安装包在 `dist/DiskSentinel/` 目录中。

- **Windows**: 双击 `DiskSentinel.exe` 运行
- **Linux**: 运行 `./DiskSentinel`
- **macOS**: 打开 `DiskSentinel.app`

## 📖 使用说明

### 1. 添加监控路径
1. 点击左侧导航栏「扫描管理」
2. 点击「添加监控路径」
3. 选择要监控的目录
4. 可配置排除规则（如 `*.tmp, node_modules`）
5. 选择触发方式：手动 / 定时

### 2. 执行扫描
- **手动扫描**: 在扫描管理页面点击「立即扫描」
- **定时扫描**: 配置时选择「按间隔」或「每天定时」

### 3. 查看变化
- **仪表盘**: 查看总览统计和趋势图
- **历史记录**: 查看每次扫描的详细变化
- **实时监控**: 开启后实时查看文件事件

### 4. 导出报告
- 在历史记录页面选择扫描记录
- 点击「导出 CSV」或「导出 HTML」

## 📁 项目结构

```
disk-sentinel/
├── main.py              # 应用入口
├── build.py             # 打包脚本
├── requirements.txt     # 依赖列表
├── docs/                # 文档
└── src/
    ├── app.py           # Flet 应用主体
    ├── core/            # 核心业务逻辑
    │   ├── database.py  # 数据库管理
    │   ├── snapshot.py  # 快照引擎
    │   ├── watcher.py   # 实时监控
    │   ├── scheduler.py # 定时任务
    │   └── reporter.py  # 报表生成
    ├── ui/              # UI 页面
    │   ├── dashboard.py # 仪表盘
    │   ├── scanner.py   # 扫描管理
    │   ├── monitor.py   # 实时监控
    │   ├── history.py   # 历史记录
    │   └── settings.py  # 设置
    └── utils/           # 工具函数
        ├── format.py    # 格式化
        └── platform_utils.py # 平台工具
```

## 📄 许可证

MIT License
