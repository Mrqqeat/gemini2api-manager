# Gemini 多账号管理助手 (Gemini Manager)

本项目是一个基于 FastAPI 的 Gemini 代理服务器增强版。它不仅能将 Google 的 Gemini 模型转换为兼容 OpenAI 的接口，还加入了一个强大的 **Web 可视化管理后台**，支持多账号平滑管理、多端口独立配置以及实时额度监控。

> **核心优势**：支持 **CLI** 与 **Antigravity** 双协议，告别繁琐的命令行配置，多账号额度一目了然。

---

## 📸 界面预览

![服务管理展示图](https://i.postimg.cc/152P2X7T/QQ-jie-tu20251221161557.jpg)
![额度监控展示图](https://i.postimg.cc/wjLqzLJ7/V3V-Q-8VG7-EH5Y9D-I26.png)
![额度监控展示图](https://i.postimg.cc/wB9pdPgw/QQ-jie-tu20260108225842.jpg)

---

## ✨ 核心功能

- 🖥️ **可视化面板**：提供直观的 Web 界面（默认 3000 端口），支持拖拽排序和一键启停。
- 👥 **多账号管理**：支持导入多个 Google 凭证，支持 **CLI** 和 **Antigravity** 两种授权类型。
- 📊 **智能额度监控**：实时计算各模型分组的剩余次数，支持自动识别账号等级（Pro/普通）。
- 🔌 **双模式接口**：
    - **OpenAI 兼容模式**：提供 `/v1/chat/completions` 接口。
    - **Native Gemini 模式**：完整转发 Google 官方 API 路径。
- 🧠 **高级变体支持**：支持 `-search`（搜索）、`-maxthinking`（最大思维链）、`-nothinking`（禁用思考）。

---

## 📈 配额与使用规则

### 1. Gemini CLI 模式 (每日重置额度)
| 模型分组 | 对应模型范围 | Pro 账号额度 | 非 Pro (内测项目) |
| :--- | :--- | :--- | :--- |
| **Flash 组** | 2.0-flash, 2.5-flash, 2.5-flash-Lite | 1500 次 | 1000 次 |
| **3-Flash 组** | 3-Flash-Preview | 1500 次 | 1000 次 |
| **Pro 组** | 2.5-Pro, 3-Pro-Preview | 250 次 | 100 次 |

> **注意**：
> - **Pro 用户**：可使用自己账号下可用的谷歌云 Project ID。
> - **非 Pro 用户**：若使用“自己账号下的谷歌云项目 ID”（非cli加入的内测项目 ID），将**无法访问 3.0 系列模型**，其余配额同上。

---

### 2. Google Antigravity 模式 (每 6 小时重置额度)
| 模型分组 | 对应模型范围 | Pro 账号额度 |
| :--- | :--- | :--- |
| **2.5 Flash 组** | 2.5-flash, 2.5-flash-thinking | 3000 次 |
| **2.5 Lite 组** | 2.5-flash-lite | 5000 次 |
| **3.0 Flash 组** | 3-flash | 400 次 |
| **3.0 Pro 组** | 3-pro-low, 3-pro-high | 320 次 |
| **3.0 Image 组** | 3-pro-image | 20 次 |
| **Claude/GPT 组** | Claude 3.5/4.5, GPT-OSS | 150 次 |
| **其他模型组** | rev19-uic3-1p | 500 次 |

> **账号分类说明**：
> - **Pro 账号**：享受上述高频配额，每 6 小时重置一次。
> - **非 Pro (使用内测项目)**：由于内测项目是公共项目，所以**无固定次数限制**（随便用），但部分高级模型不可用。
> - **非 Pro (使用自己的谷歌云项目)**：目前官方已停用此组合，**无法使用**。

---

## 🛠️ 快速开始

### 1. 安装环境
```bash
git clone https://github.com/Mrqqeat/gemini2api-manager.git
cd gemini2api-manager
pip install -r requirements.txt
```

### 2. 获取凭证 (Tokens)
- **手动方式**：将生成的 `email.json` 放入 `tokens/cli/` 或 `tokens/antigravity/` 目录。
- **自动方式**：启动管理后台后，直接在网页点击 **“登录添加”** 按钮，按照 Google 提示完成 OAuth 授权。

### 3. 运行
```bash
python manager.py
```
访问：**`http://localhost:3000`**

---

## 📖 使用指南

### 添加服务
1. 点击 **“添加服务”**。
2. 选择 **服务类型**（CLI 或 Antigravity）。
3. **Project ID 探测**：点击刷新图标，系统会自动拉取该账号下加入的内测项目、所拥有的谷歌云项目。
4. 设置端口和密码并启动。

### 模型后缀说明
调用 API 时，可以通过模型名后缀开启高级功能：
- `...-search`: 强制开启谷歌搜索。
- `...-maxthinking`: 强制分配最大思考预算。
- `...-nothinking`: 彻底禁用思考过程以节省输出速度。

---

## 📂 项目结构
```text
├── manager.py          # Web 管理后台
├── run_proxy.py        # 代理服务启动器
├── tokens/             
│   ├── cli/            # 存放 CLI 协议凭证
│   └── antigravity/    # 存放 Antigravity 协议凭证
├── src/                # 核心转发逻辑
└── static/templates/   # 前端资源
```

---

## 🤝 鸣谢
本项目核心转发逻辑基于 [geminicli2api](https://github.com/gzzhongqi/geminicli2api) 二次开发，感谢原作者。

---

## 📄 开源协议
[MIT License](LICENSE)
