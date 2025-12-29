import sys
import os
from typing import Optional, Dict, List

# --- AgentScope ---
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.model import OpenAIChatModel, DashScopeChatModel
from agentscope.memory import InMemoryMemory, Mem0LongTermMemory
from agentscope.embedding import DashScopeTextEmbedding
# 确保引入了 Formatter
from agentscope.formatter import DeepSeekChatFormatter

# --- 项目模块 ---
from src.core.load_model import load_model_config
from src.config.prompts import SCHEDULE_SYSTEM_PROMPT
from src.tools.lark_tools import LarkTool
from src.tools.note_tools import AgentNotebook
from src.tools.clock_tool import ClockTool


class ScheduleAgent(ReActAgent):
    """
    全封装 Agent：内部自动组装模型、记忆和工具。
    """

    def __init__(self, name: str = "Scheduler"):
        # 1. === 加载配置 ===
        app_id = os.environ.get("SCHEDULER_APP_ID")
        app_secret = os.environ.get("SCHEDULER_APP_SECRET")
        user_open_id = os.environ.get("USER_OPEN_ID")

        if not app_id or not app_secret:
            raise ValueError("❌ 环境变量缺失: SCHEDULER_APP_ID 或 SCHEDULER_APP_SECRET")

        config_args = load_model_config("deepseek_config")
        config_args.pop("config_name", None)
        config_args.pop("model_type", None)

        print(f"🏭 [Agent内部] 正在组装大脑 (Model: {config_args.get('model_name')})...")
        model_instance = OpenAIChatModel(**config_args)

        # 2. === 组装工具 ===
        print("🛠️ [Agent内部] 正在组装四肢 (Tools)...")
        toolkit = Toolkit()
        lark_tool = LarkTool(app_id, app_secret, user_open_id)
        notebook = AgentNotebook(agent_name=name)
        clock_tool = ClockTool()

        tools_list = [
            # 飞书能力
            lark_tool.get_calendar_events,
            lark_tool.create_calendar_event,
            lark_tool.delete_calendar_event,
            lark_tool.get_tasks,
            lark_tool.create_task,
            lark_tool.delete_task,
            lark_tool.debug_user_identity,
            # 记忆能力
            notebook.read_notebook,
            notebook.record_task,
            notebook.update_task_status,
            notebook.add_pattern,
            notebook.promote_pattern_to_memory,
            notebook.update_project_status,
            # 感知能力
            clock_tool.get_current_datetime,
        ]

        for tool in tools_list:
            toolkit.register_tool_function(tool)

        # 3. === 组装长期记忆 ===
        print("🧠 [Agent内部] 正在连接海马体 (Long Term Memory)...")
        dashscope_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("OPENAI_API_KEY")

        scheduler_memory = Mem0LongTermMemory(
            agent_name=name,
            user_name="User",
            model=model_instance,
            embedding_model=DashScopeTextEmbedding(
                model_name="text-embedding-v2",
                api_key=dashscope_key,
            ),
            on_disk=True,
        )

        # 4. === 激活父类 (Agent 出生) ===
        super().__init__(
            name=name,
            sys_prompt=SCHEDULE_SYSTEM_PROMPT,
            model=model_instance,

            # ⚡️ 【修复点】补上了 formatter
            # 告诉 Agent 使用 DeepSeek/OpenAI 风格的 ReAct 格式
            formatter=DeepSeekChatFormatter(),

            toolkit=toolkit,
            memory=InMemoryMemory(),
            long_term_memory=scheduler_memory,
            long_term_memory_mode="both",
            max_iters=15,
        )

        # 5. === 挂载属性 (方便外部调用工具进行测试，非必须) ===
        self.lark_tool = lark_tool
        self.notebook = notebook
        self.clock_tool = clock_tool

        print("✅ [Agent内部] 机器人组装完毕！")