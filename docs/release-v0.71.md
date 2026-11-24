# LMU Data Analysis V0.71

V0.71 将「车手成长」改为按赛道布局回看每场录制。不同车型和会话类型可以放在同一张图和明细表中查看。

## 新增与改进

- **车手成长**展示每场最快圈和最快 5 圈平均。悬停可查看对应车型、时间和圈时，明细表中的最快圈可直接打开。
- **自适应横轴**按录制时间排序并等距排布。刻度随可用宽度调整，密集录制可以横向滚动。
- **桌面界面**细化深色卡片、导航选中状态和线条图标。
- **公开文档**补齐快速开始、用户指南、常见问题、构建和迁移步骤。项目采用 GNU GPL 第 3 版。

## 下载与升级

从 Assets 下载 `LMU-Data-Analysis-v0.71-win-x64.zip`，完整解压后运行 `LMU-Data-Analysis-v0.71.exe`。需 64 位 Windows 和 Microsoft Edge WebView2 Runtime。升级时先退出旧版，同一 Windows 账号可继续读取已有本地档案。

随附的 `LMU-Data-Analysis-v0.71-win-x64.zip.sha256` 可用于核对下载文件的 SHA-256。

最快 5 圈平均只使用有圈时且无已知进站状态的完整圈。少于 5 个统计圈时，明细保留最快圈，平均值显示为「—」。

[用户指南](https://github.com/Saturday-365/LMU_Data_Analysis/blob/v0.71/docs/desktop-v0.71.md) · [对应源码](https://github.com/Saturday-365/LMU_Data_Analysis/tree/v0.71) · [问题反馈](https://github.com/Saturday-365/LMU_Data_Analysis/issues)
