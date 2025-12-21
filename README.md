---

# Gemini 多账号管理助手 (Gemini Manager)

本项目是一个基于 FastAPI 的 Gemini 代理服务器增强版。它不仅能将 Google 的 Gemini 模型转换为兼容 OpenAI 的接口，还加入了一个强大的 **Web 可视化管理后台**，支持多账号平滑管理、多端口独立配置以及实时额度监控。

> **核心优势**：告别繁琐的命令行和环境变量配置，一切操作均可在浏览器中完成。

---

## 📸 界面预览

![服务管理展示图](https://i.postimg.cc/152P2X7T/QQ-jie-tu20251221161557.jpg)
![额度监控展示图](https://i.postimg.cc/D0DV9p6Q/QQ-jie-tu20251221161738.jpg)

---

## ✨ 核心功能

- 🖥️ **可视化面板**：提供直观的 Web 界面（默认 3000 端口），支持拖拽排序和一键启停。
- 👥 **多账号管理**：支持导入多个 Google 凭证（JSON 文件），为不同账号分配独立端口。
- 📊 **额度监控**：实时查看各账号的 `Pro` 和 `Flash` 模型剩余额度、重置时间及账号等级（Pro/普通）。
- 🔌 **双模式接口**：
    - **OpenAI 兼容模式**：提供 `/v1/chat/completions` 接口，支持主流 AI 客户端。
    - **Native Gemini 模式**：完整转发 Google 官方 API 路径。
- 🧠 **高级配置**：支持 `-search`（谷歌搜索）、`-maxthinking`（最大思维链）等模型变体。
- 🖼️ **多模态支持**：完美处理文本、图片输入及流式输出。

---

## 🛠️ 快速开始

### 1. 环境准备
确保你的电脑已安装 Python 3.9+，然后克隆本项目并安装依赖：

```bash
git clone https://github.com/Mrqqeat/geminicli2api-manager.git
cd geminicli2api-manager
pip install -r requirements.txt
```

### 2. 准备凭证 (Tokens)
本项目通过读取 `tokens/` 目录下的 JSON 凭证文件来运行。
1. 在项目根目录下创建 `tokens` 文件夹。
2. 使用 `gemini-cli` 或其他工具完成 Google OAuth 登录。
3. 将生成的凭证 JSON 文件（包含 `client_id`, `refresh_token` 等信息）放入 `tokens/` 目录。

### 3. 启动管理面板
运行以下命令启动 Web 管理后台：

```bash
python manager.py
```
启动后，在浏览器访问：**`http://localhost:3000`**

---

## 📖 使用指南

### 添加代理服务
1. 在 Web 面板点击 **“添加服务”**。
2. **凭证文件**：下拉选择你放入 `tokens/` 目录的 JSON 文件。
3. **Project ID**：输入或从下拉列表选择你的 Google Cloud 项目 ID。
4. **端口 & 密码**：为该账号设置独立的监听端口及访问密码（用于 API 调用鉴权）。
5. 点击保存后，在列表点击 **“启动服务”**。

### API 调用 (OpenAI 格式)
服务启动后，你可以使用任何 OpenAI 客户端进行调用：
- **Base URL**: `http://localhost:你的端口/v1`
- **API Key**: 你在面板设置的密码
- **模型名称示例**: 
    - `gemini-2.5-pro-maxthinking` (开启深度思考)
    - `gemini-2.5-flash-search` (开启谷歌搜索)

---

## 📂 项目结构

```text
├── manager.py          # Web 管理后台主程序
├── run_proxy.py        # 代理服务运行脚本
├── tokens/             # 存放 Google OAuth 凭证 JSON (手动创建)
├── servers_config.json # 系统自动生成的服务器配置
├── src/                # 代理转发核心代码
└── templates/          # 可视化面板前端页面
```

---

## 🤝 鸣谢

本项目基于 [原作者项目名](原项目链接) 进行深度二次开发，感谢原作者在 Gemini 接口转发上的贡献。

---

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 协议发布。

---
