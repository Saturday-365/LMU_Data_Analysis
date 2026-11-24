# LMU 个人遥测工作台 · 桌面 V0.51

解压整个发行目录后，双击 `LMU-Data-Analysis-v0.51.exe`。需要 Windows 64 位及 Microsoft Edge WebView2 Runtime。可直接打开旧版档案。

## 圈速导出

在「个人赛道档案」点击「导出全部圈速 CSV」，选择保存位置。文件可用 Excel 打开，包含当前本地档案的全部完整圈。录制时间统一为 UTC，文件中的源圈号和软件显示的完整圈序号分别列出。缺失的官方圈时留空，进站状态和是否计入节奏分别标明。

导入时仍会拒绝内容相同的文件，过滤录制时长不足 60 秒或没有完整圈的录制。

## 构建

在 PowerShell 中运行 `.\scripts\build-desktop.ps1`。发行目录为 `dist/LMU-Data-Analysis-v0.51/`，分发时保留整个目录。
