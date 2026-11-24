# LMU 个人遥测工作台 · 桌面 V0.46

解压整个发行目录后，双击 `LMU-Data-Analysis-v0.46.exe`。需要 Windows 64 位及 Microsoft Edge WebView2 Runtime。旧版的本地档案可直接打开，之前导入失败的遥测可在新版重新导入。

## 遥测导入

- 支持 GPS 采样时钟中的向前间断。保留原始时间戳、完整圈和官方圈时，驾驶曲线及 GPS 走线在间断处断开。
- 读取提示会显示采样间断次数和最长间隔。重复或回退的时间戳仍会触发导入错误。

首页提供个人赛道档案，包含最近正赛、驾驶段和按赛道整理的排位与正赛表现。

## 构建

在 PowerShell 中运行 `.\scripts\build-desktop.ps1`。发行目录为 `dist/LMU-Data-Analysis-v0.46/`，分发时保留整个目录。
