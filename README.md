
---

# ScheduleAgent 使用说明

本项目是一个基于 AgentScope 的飞书自动化办公智能体，支持自动管理飞书任务清单、创建日历日程以及记录本地运行笔记。

## 1. 环境准备

### 依赖安装

推荐使用 Python 3.10+ 环境。在项目根目录下执行：

```bash
pip install -r requirements.txt

```

### 飞书应用权限

请确保你的飞书自建应用已开通以下权限：

* **任务**：查看、创建、更新、删除任务，查看及创建清单。
* **日历**：更新日历及日程信息。
* **通讯录**：获取用户 user ID（用于识别 `USER_OPEN_ID`）。

## 2. 配置文件 (.env)

由于安全原因，`.env` 文件已被 `.gitignore` 忽略。**你需要在项目根目录下手动创建一个名为 `.env` 的文件**，并填入以下内容：

```env
# --- 大模型 API 配置 ---
# DeepSeek API Key
DEEPSEEK_API_KEY=你的Key内容

# DashScope (通义千问) API Key
DASHSCOPE_API_KEY=你的Key内容

# --- 飞书机器人配置 ---
# 飞书应用的 App ID 和 App Secret
LARK_APP_ID=你的AppID
LARK_APP_SECRET=你的AppSecret

# 你的个人飞书 Open ID (Agent 将任务指派给你)
LARK_USER_OPEN_ID=你的OpenID

```

## 3. 运行指南

### 启动程序

```bash
python src/launch.py

```

### 功能说明

* **任务管理**：Agent 启动后会检查是否存在名为 `🤖 Agent 协作清单` 的清单。如果没有，它会自动创建并把你拉入协作。所有的任务都会创建在此清单内。
* **日历同步**：Agent 创建日程后，会自动将你添加为参与人。你需要去飞书日历查看邀请并确认。
* **本地笔记**：Agent 的运行状态、待办历史和规律总结会自动保存在 `data/notebook_Scheduler.json` 中。

## 4. 注意事项

* **时间戳说明**：本项目已处理飞书任务（毫秒）与日历（秒）之间的时间戳差异，调用工具时直接传入标准时间格式（如 `2025-12-30 10:00:00`）即可。
* **环境变量名**：请确保 `.env` 中的变量名与 `LarkTool` 初始化时的读取逻辑保持一致。

---
