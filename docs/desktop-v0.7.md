# LMU 个人遥测工作台 · 桌面 V0.7

## 启动

完整解压 `LMU-Data-Analysis-v0.7-win-x64.zip` 后，双击 `LMU-Data-Analysis-v0.7.exe`。请保留同目录下的 `_internal/` 和随包文件。运行环境为 64 位 Windows 和 Microsoft Edge WebView2 Runtime。

## 车手成长

打开「个人圈速 → 车手成长」，选择赛道布局、车辆、组别和会话类型组成的比较组合。已有档案和新导入录制都会参与计算。

- **个人最佳**对照该组合的最早录制。刷新纪录时，里程碑记录当时的圈时和比前纪录快了多少。
- **最近中位圈速**和**最近圈速波动**比较最早与最近的可统计会话，各需至少 3 个统计圈。圈速波动使用标准差。
- **进步曲线**同时显示各场最快圈、中位圈和截至该场的历史最佳。点击图中某个录制位置或使用「查看录制」选择器，可查看对应数据并跳到最快圈。

成长页使用带时间的录制，并沿用档案的完整圈和进站过滤口径。车辆优先使用车型，缺少车型时按完整车辆条目分组。圈时会受天气、轮胎和油量影响。接力文件按整份录制汇总，需结合实际驾驶时段判断个人成绩。

## 导入和回看

点击侧栏的「批量导入遥测」，或将游戏生成的 `.duckdb` 文件拖入导入区。「设置」可配置游戏遥测目录，保存后软件会在启动时扫描，也能选择「立即扫描」。导入会拒绝重复文件，并过滤时长不足 1 分钟或少于 1 个完整圈的录制。

在「赛道总览」右侧选择最近录制，左侧会更新会话预览和圈速分布。点击「打开会话」进入分析页。

## 升级和备份

退出旧版后，将新版解压到独立目录再启动。同一 Windows 账号默认使用 `%LOCALAPPDATA%\LMU Data Analysis`。如果旧版通过 `--data-dir` 指定了档案目录，启动新版时继续使用同一路径。

关闭软件后可复制整个档案目录进行备份。目录包含 `catalog.sqlite3`、`recordings/`、赛道资源和本机设置。

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

构建生成 `dist/LMU-Data-Analysis-v0.7/`。可直接运行目录内的 EXE，也可压缩整个目录后传给另一台电脑。

后续更新源码时，退出桌面程序，在仓库根目录执行 `git switch main` 和 `git pull --ff-only`，再安装最新的桌面依赖并运行构建脚本。
