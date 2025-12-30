
---

# 📝 Agent Team 项目使用说明

本项目是一个基于 **AgentScope** 与 **飞书 (Lark)** 构建的自律任务管理智能体集群。通过飞书机器人，智能体能够自动管理你的日程、任务清单，并以“管理合伙人”的身份为你提供晨报、午报及晚报服务。

## 1. 🚀 飞书开放平台设置指南

要运行此 Agent，你需要在飞书开放平台创建一个自建应用。

### 第一步：创建应用

1. 登录 [飞书开放平台](https://open.feishu.cn/app?lang=zh-CN)。
2. 点击 **“创建自建应用”**，填写名称（如：调度官）并上传图标。

### 第二步：获取凭证 (App ID & App Secret)

1. 在左侧菜单栏选择 **“凭证与基础信息”**。
2. 你可以在此处找到 **App ID** 和 **App Secret**。请将其妥善保管，后续需填入 `.env` 文件。

### 第三步：开启机器人能力

1. 在左侧菜单中找到 **“应用功能” -> “机器人”**。
2. 点击 **“启用机器人”**。这是 Agent 与你聊天的前提。

### 第四步：配置事件订阅 (长连接模式)

1. 进入 **“事件订阅”**。
2. 推荐选择 **“使用长连接”**。这种模式下，Agent 可以在本地或 NAS 运行，无需公网 IP 即可接收消息。

### 第五步：开通权限 (重要)

在 **“权限管理”** 中，搜索并开通以下权限：

* **消息内容读取权限**：`im:message:p2p_msg:readonly` (读取私聊消息) 和 `im:message.group_msg:readonly` (读取群聊消息)。
* **发送消息**：`im:message:send_as_bot`。
* **日历**：`calendar:calendar:readonly` 和 `calendar:calendar` (管理日程)。
* **任务**：`task:task` (管理清单与任务)。
* **通讯录**：`contact:user.employee_id:readonly` (获取你的 Open ID，以便 Agent 主动找你)。

### 第六步：发布应用

1. 点击 **“版本管理与发布”**。
2. 创建版本并申请上线。如果是个人使用，管理员审核通过后即可生效。

---

## 2. 🛠️ 快速开始

### 依赖安装

推荐使用 Python 3.10+ 环境。

```bash
pip install -r requirements.txt

```

### 环境变量配置

在项目根目录创建 `.env` 文件，格式如下：

```env
# --- 大模型配置 ---
DEEPSEEK_API_KEY=你的Key
DASHSCOPE_API_KEY=你的Key (用于Embedding)

# --- 调度官 (Scheduler) 配置 ---
# 此处的前缀与 launch.py 中的工厂方法对应
SCHEDULER_APP_ID=从飞书获取的AppID
SCHEDULER_APP_SECRET=从飞书获取的AppSecret

# 你的个人飞书 Open ID (用于接收定时报告)
USER_OPEN_ID=你的OpenID

```

### 启动服务

现在的系统采用工厂模式，一键启动所有就绪的 Agent：

```bash
python src/launch.py

```

---

## 3. 🧠 核心功能架构

* **多 Agent 工厂**：支持在 `launch.py` 中通过配置快速扩展 Coder、Searcher 等新 Agent。
* **飞书收发器**：内置 `LarkManager` 处理消息清洗与 Markdown 卡片回复。
* **生命周期自治**：Agent 自主管理“开启、响应、定时、退出”逻辑。
* **三层存储笔记本**：
* `Memento`：跨会话的自我交代，确保 Agent 醒来后能接上进度。
* `Tasks`：待办任务管理。
* `Calendars`：日程记录，自动与飞书日历同步。



---

## 4. 📂 项目结构

* `src/launch.py`: 系统总入口。
* `src/agents/`: 存放各 Agent 的思考逻辑与生命周期定义。
* `src/core/`: 核心连接器，包含飞书通讯与模型加载逻辑。
* `src/tools/`: Agent 可调用的工具集（飞书工具、笔记本、时钟）。
* `src/utils/`: 时间戳转换等通用工具。

---
