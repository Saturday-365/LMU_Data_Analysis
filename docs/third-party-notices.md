# 第三方许可与声明

V0.71 Windows 包附带 Python 运行时、应用所需的 Python 库以及桌面窗口的桥接组件。第三方组件适用各自的许可。[项目许可证](https://github.com/Saturday-365/LMU_Data_Analysis/blob/v0.71/LICENSE)

| 组件 | 来源和许可说明 |
| --- | --- |
| CPython | 运行时及其附带组件。发行包的 `licenses/CPython/` 包含 Python 安装自带的许可文件。[Python 许可](https://docs.python.org/3.12/license.html) |
| DuckDB、FastAPI、Uvicorn、pywebview 及其依赖 | 运行包保留相应 Python 发行版自带的许可证或声明，按组件与版本存放于 `licenses/`。依赖版本见源码中的 `requirements-desktop.txt` 和其引用的清单。 |
| PyInstaller | 打包器的启动加载器及相关组件，适用上游启动加载器例外。许可说明随包附带。[PyInstaller 许可](https://pyinstaller.org/en/stable/license.html) |
| proxy_tools | 发行包保存上游 BSD 文本。[上游许可证](licenses/proxy-tools.txt) |
| Microsoft Edge WebView2 | 发行包内包含 pywebview 使用的 WebView2 SDK 组件。Windows 用户需安装 WebView2 Runtime。[SDK 许可](licenses/WebView2-SDK-LICENSE.txt) · [SDK 声明](licenses/WebView2-SDK-NOTICE.txt) |

应用绘制的车辆走线来自导入的遥测，界面文档示例使用模拟数据。Le Mans Ultimate 名称用于指明兼容的游戏。[项目参考资料](https://github.com/Saturday-365/LMU_Data_Analysis/blob/v0.71/docs/references.md)
