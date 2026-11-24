# LMU 个人遥测工作台 · 桌面 V0.56

解压整个发行目录后，双击 `LMU-Data-Analysis-v0.56.exe`。需要 Windows 64 位及 Microsoft Edge WebView2 Runtime。

## 圈速分布

从档案打开录制，进入「节奏与调教」。圈速分布位于「逐圈节奏」和「连续驾驶段」之间，用同一圈时横轴显示整场和各驾驶段，便于对照快慢及波动。驾驶段颜色与逐圈节奏图一致。

竖线标明中位圈，两端为最快和最慢圈。每行至少有 5 圈时显示 P10–P90 色带。缺少可靠驾驶段的录制显示整场分布。

## 构建

在 PowerShell 中运行 `.\scripts\build-desktop.ps1`。发行目录为 `dist/LMU-Data-Analysis-v0.56/`，分发时保留整个目录。
