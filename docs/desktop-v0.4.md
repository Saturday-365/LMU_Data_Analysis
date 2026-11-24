# LMU 个人遥测工作台 · 桌面 V0.4

解压整个发行目录，双击 `LMU-Data-Analysis-v0.4.exe`。需要 Windows 64 位及 Microsoft Edge WebView2 Runtime。旧版本录制、练习补录和保存的区间可直接读取。

## 首页

「赛道总览」按赛道布局列出录制数、完整圈数、参与节奏统计的圈数和最近录制时间。表格区分练习、排位与正赛，按品牌和组别展示最快圈、中位圈与 P10–P90。中位圈从参与统计的单圈合并计算，P10–P90 至少需要五圈。分组信息缺失时记录圈数。点击品牌查看该组的历史趋势，点击最快圈可直接进入曲线。

## 品牌

品牌优先使用「练习信息」中的手工补录，然后识别已填车型或原始车辆标识。对经过核对的涂装使用本地映射。例如 Proton Competition 的 2026 勒芒 #77 归 Ford，同年的 ELMS #75 归 Porsche。涂装原文保留在会话和练习信息内。部分 Logitech G Challenge 专用涂装缺少可确认的品牌，显示为「未识别品牌」。所有圈时统计仍来自已导入的本地遥测。

参赛信息依据 [2026 FIA WEC 参赛车辆](https://www.fiawec.com/en/car/2026)、[2026 勒芒参赛名单](https://www.fiawec.com/en/race/document/download/2329)、[2025 WEC 参赛车辆](https://www.fiawec.com/en/page/awesome-competitors/13)、[2026 ELMS 参赛名单](https://www.europeanlemansseries.com/en/race/document/download/2337)和 [2024 勒芒 JMW 记录](https://www.24h-lemans.com/en/track-record/teams/j)。

## 区间标记

选好当前圈和参考圈后，点击曲线上方的「标记区间」，在任意一条曲线上拖选，或在曲线或走线上依次点两端。选中区域会同步高亮，完成后直接进入区间复盘。可按 Esc 取消，也可用左右方向键移动曲线游标并按 Enter 标记。数值输入仍可用于精确调整。

## 构建

在项目根目录运行 `.\scripts\build-desktop.ps1`。发行目录为 `dist/LMU-Data-Analysis-v0.4/`，分发时保留整个目录。
