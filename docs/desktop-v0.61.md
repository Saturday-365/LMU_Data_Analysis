# LMU 个人遥测工作台 · 桌面 V0.61

## 启动

完整解压 `LMU-Data-Analysis-v0.61-win-x64.zip` 后，双击 `LMU-Data-Analysis-v0.61.exe`。请同时保留同目录下的 `_internal/` 和随包文件。运行环境为 64 位 Windows 和 Microsoft Edge WebView2 Runtime。

## 首页和设置

V0.61 在原有深色界面中为导航、导入、搜索、分析标签和设置操作增加线条图标。铜橙色标出当前选择和「打开会话」按钮。

在首页右侧选择一条最近录制，左侧随即更新圈数、节奏、进出站和圈速分布。点击「打开会话」进入该录制的「节奏与调教」页。

在「设置」选择游戏遥测目录并保存。软件启动时按更新时间扫描该目录直接包含的 `.duckdb` 文件，也可点击「立即扫描」。导入会按内容去重，并过滤时长不足 1 分钟或少于 1 个完整圈的录制。将路径留空并保存可关闭启动扫描。

## 升级和备份

退出旧版后，将新版解压到独立目录再启动。同一 Windows 账号下默认使用 `%LOCALAPPDATA%\LMU Data Analysis`。如果旧版通过 `--data-dir` 指定了档案目录，启动新版时继续使用同一路径。

备份时请关闭软件，并复制整个档案目录。目录包含 `catalog.sqlite3`、`recordings/`、赛道资源和本机设置。

## 迁移到另一台电脑

1. 退出软件，将整个档案目录复制到新电脑对应 Windows 账号的 `%LOCALAPPDATA%`。如果新电脑已有档案，先分别备份。
2. 启动新版 EXE，确认会话和曲线可以打开。
3. 如果游戏遥测路径有变化，在「设置」重新选择目录并保存。

## 构建

在安装了 Git 和 Python 3.12 的 Windows 电脑上，可从仓库构建桌面版。

```powershell
git clone https://github.com/Saturday-365/LMU_Data_Analysis.git
Set-Location LMU_Data_Analysis
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\scripts\build-desktop.ps1
```

构建生成 `dist/LMU-Data-Analysis-v0.61/`。可直接运行目录内的 EXE，也可压缩整个目录后传给另一台电脑。

后续更新源码时，退出桌面程序，在仓库根目录执行 `git switch main` 和 `git pull --ff-only`，再安装最新的桌面依赖并运行构建脚本。
