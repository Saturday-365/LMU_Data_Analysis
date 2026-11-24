# LMU 个人遥测工作台 · 桌面 V0.6

## 启动

将 `LMU-Data-Analysis-v0.6-win-x64.zip` 复制到目标电脑。完整解压后，双击 `LMU-Data-Analysis-v0.6.exe`，请同时保留同目录下的 `_internal/` 和随包文件。运行环境为 64 位 Windows 和 Microsoft Edge WebView2 Runtime。

Git 仓库提供源码和构建脚本。取得 ZIP 后可以直接运行，需要自行生成 EXE 时使用本文的构建步骤。

## 首页预览

在首页右侧「最近录制」选择一条记录。左侧预览会更新圈数、节奏、进出站和圈速分布。点击左侧「打开会话」后进入该录制的「节奏与调教」页。

## 启动时导入

在「设置」选择或输入游戏遥测目录，然后保存。每次启动会扫描目录直接包含的 `.duckdb` 文件，按文件更新时间从新到旧处理。首次扫描会导入符合条件的历史文件，之后会跳过已经处理且未变更的文件。设置页也可点击「立即扫描」，查看新增、重复、过滤和待重试结果。

自动导入复用手动导入的内容去重、文件大小、最短录制时长和完整圈规则。正在写入或复制期间发生变化的文件留待之后扫描。原始文件保存在游戏目录，档案使用导入副本。

将路径留空后保存即可停用启动扫描。扫描期间更改路径会应用到下一次扫描。

## 迁移到另一台电脑

桌面 EXE 默认使用当前 Windows 账号下的 `%LOCALAPPDATA%\LMU Data Analysis`。如果以 `--data-dir` 启动，则以该参数指定的目录为准。

1. 退出旧电脑上的软件。在资源管理器地址栏输入 `%LOCALAPPDATA%`，复制其中整个 `LMU Data Analysis` 文件夹。
2. 在新电脑首次打开软件前，把该文件夹放到新电脑当前账号的 `%LOCALAPPDATA%`。如果新电脑已经有自己的档案，先将两份档案分别保存，避免覆盖其中一份。
3. 启动新电脑的 EXE，确认会话列表和曲线可打开。如果用于自动导入的游戏目录变了，在「设置」重新选择路径并保存。

整个档案目录包含 `catalog.sqlite3`、`recordings/`、赛道资源及本机设置。圈次编号、补录和保存的区间在目录数据库中，曲线使用 `recordings/` 中的遥测副本。游戏目录里尚未导入的原始遥测可另行复制。

## 升级发行版

1. 退出旧版。备份时请复制整个本地档案目录。
2. 把新版 ZIP 解压到独立目录，运行其中的新版 EXE。使用同一 Windows 账号和默认数据目录时，新版会读取已有档案。如果此前用了 `--data-dir`，启动新版时继续指定原目录。
3. 确认新版能读取会话和曲线后，可以删除旧版解压目录。软件发行目录和本地档案目录分别保存。

## 构建

在有仓库访问权限的电脑上安装 Git 和 Python 3.12。在 PowerShell 中克隆并构建。

```powershell
git clone https://github.com/Saturday-365/LMU_Data_Analysis.git
Set-Location LMU_Data_Analysis
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\scripts\build-desktop.ps1
```

V0.6 的构建目录为 `dist/LMU-Data-Analysis-v0.6/`。可运行目录中的 EXE，或把整个目录压缩后传给另一台电脑。

后续从 `main` 更新时，先退出正在运行的桌面程序，再在仓库根目录运行以下命令。

```powershell
git switch main
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\scripts\build-desktop.ps1
```

运行 `dist/` 下新版本目录里的 EXE。拉取操作更新仓库源码，构建完成后才会生成新的桌面程序。
