# 霜璃桌宠

> **推荐让熟悉 Windows 与 ChatGPT 配置的 Agent 帮忙安装和连接。** 把本仓库地址与 [启动与连接指南](docs/连接与启动.md) 发给 Agent，让它在下载者自己的电脑上完成依赖、构建、本机插件和隧道配置；密钥只在下载者本机输入。

霜璃是 Windows 11 上的透明桌面小龙娘。她会跟随、闲逛、休息，回应抚摸与拖拽；桌面输入条和气泡可以接入下载者自己的 ChatGPT 聊天。角色和界面在离线状态也可使用。

## 获取与启动

下载仓库源码后，按 [启动与连接指南](docs/连接与启动.md) 创建 Python 环境并构建 Windows 程序。运行 `dist/ShuangliCompanion/ShuangliCompanion.exe`，也可以在根目录双击 `start.cmd`。本仓库不提交本机生成的 `dist`、`.venv` 和 `data`。

触碰角色可展开输入条，Enter 发送；右键打开设置。拖动角色可抛掷，Ctrl 加滚轮缩放。Ctrl+Alt+Shift+D 恢复角色，Ctrl+Alt+Shift+C 打开输入条。

## ChatGPT 连接

原聊天连接使用本机 `desktop_mcp.py`、OpenAI Secure MCP Tunnel 和 ChatGPT 中下载者自己登记的 MCP 插件。每位下载者需要自己的 ChatGPT/Platform 账户、隧道和运行密钥。本项目不附带账户、密钥或会话。连接步骤见 [桌面聊天插件](docs/桌面聊天插件.md)。未连接时可以保留草稿并打开 ChatGPT。

## 目录

- `src/shuangli`：桌宠、互动、渲染和设置。
- `assets`：运行时动作与模型；`assets/manifest.json` 记录素材。
- `art`：美术脚本和当前可编辑源文件。
- `plugins/shuangli-desktop`、`desktop_mcp.py`：本机 MCP 插件。
- `extension`：可选的浏览器连接方式。
- `docs`：使用与开发说明、[第三方声明](docs/第三方声明.md)。

本机个人配置、日志、构建产物和下载的开发工具由 `.gitignore` 排除。
