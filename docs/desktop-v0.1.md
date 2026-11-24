# LMU 个人遥测工作台 · 桌面 V0.1

> 本页记录该历史版本。当前 `main` 的运行、换机迁移和构建步骤见 [桌面版 V0.6](desktop-v0.6.md)。

桌面版是 Windows 64 位应用。解压整个发行目录后，双击 `LMU-Data-Analysis-v0.1.exe`。运行需要 Microsoft Edge WebView2 Runtime。应用和遥测数据均可离线使用。

## 使用方法

1. 点击「批量导入遥测」，或将多个 LMU 原生 `.duckdb` 文件拖入左侧导入区。每份上限 256 MiB。成功、重复及失败原因都可在导入结果中查看。
2. 在「个人圈速」选择赛道布局、车辆和会话类型。这里按实际录制时间排列历史趋势，显示最快圈、中位圈和每次录制的圈速波动。点击个人最佳或表格里的「查看最快圈」进入分析。
3. 在「驾驶曲线」选择当前圈和参考会话，可以选择同一布局内另一份自己的录制。紫色累计时间差为当前圈减参考圈，正值表示当前圈落后。输入两个距离并点击「查看区间」，可定位曲线与走线游标，查看该段累计时间差的变化。
4. 在「练习信息」可以补录车型、天气、车况和调教说明。车型补录优先用于个人分组，缺少车型时按原始车辆标识分组。

数据默认保存在 `%LOCALAPPDATA%\LMU Data Analysis`。退出程序后，可以备份其中的 `catalog.sqlite3`、`recordings/` 和已配置的 `track-resources/`。已有网页档案可在关闭两个版本后，将旧 `data/` 整体复制到新的空目录，再通过 `--data-dir` 指定该目录。日志保存在数据目录中的 `desktop.log`。

节奏统计排除残圈、无记录圈时及含已知维修区状态的圈。LMU 官方有效性标为未知。距离数据仅在两圈的共同覆盖区间使用，缺口断开。时钟无法安全重建的录制会报告具体问题，并继续导入同批次的剩余文件。

## 构建与复验

在仓库根目录使用 PowerShell。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\scripts\build-desktop.ps1
```

输出目录为 `dist/LMU-Data-Analysis-v0.1/`，分发时需保留整个目录。

```powershell
$exe = (Resolve-Path 'dist/LMU-Data-Analysis-v0.1/LMU-Data-Analysis-v0.1.exe').Path
Start-Process -FilePath $exe -Wait -PassThru -WindowStyle Hidden -ArgumentList @(
    '--data-dir', 'outputs/desktop-test-data', '--smoke-test', 'outputs/desktop-smoke.json'
)
```

烟测使用独立数据目录，打开后台窗口检查档案页是否通过本机接口加载，并将结果写入报告。
