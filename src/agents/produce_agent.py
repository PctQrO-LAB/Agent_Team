import asyncio
import os
from typing import Optional, Dict

# AgentScope
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.model import GeminiChatModel
from agentscope.memory import InMemoryMemory, Mem0LongTermMemory
from agentscope.embedding import GeminiTextEmbedding, DashScopeTextEmbedding
from agentscope.formatter import GeminiChatFormatter
from agentscope.message import Msg

# Core & Tools
from src.core.load_model import load_model_config
from src.core.lark_manager import LarkManager
from src.core.skill_loader import register_agent_skills
from src.tools.note_tools import AgentNotebook
from src.tools.file_tools import FileTool
from src.tools.lark_message_tools import LarkMessageTool
from src.tools.lark_drive_tools import LarkDriveTool  # Added Drive Tool

from src.config.prompts import PRODUCER_SYSTEM_PROMPT
from src.utils.message_utils import normalize_message_content

try:
    from mem0.configs.base import VectorStoreConfig
except ImportError:
    pass


class ProduceAgent(ReActAgent):
    """
    [监制]
    职责：负责审核生成内容是否符合要求。
    """

    def __init__(self, name: str, toolkit: Toolkit, memory: Mem0LongTermMemory, sys_prompt: str = "", api_key: str = None):
        # 1. 加载模型 (Qwen3-VL)
        config_args = load_model_config("gemini_config", override_api_key=api_key)
        config_args.pop("config_name", None)
        model_instance = GeminiChatModel(**config_args)
        sys_prompt = PRODUCER_SYSTEM_PROMPT

        super().__init__(
            name=name,
            sys_prompt=sys_prompt,
            model=model_instance,
            formatter=GeminiChatFormatter(),
            toolkit=toolkit,
            memory=InMemoryMemory(),
            long_term_memory=None,
            long_term_memory_mode="agent_control",
            max_iters=15,
        )

        self.manager: Optional[LarkManager] = None
        self.current_chat_id: Optional[str] = None

        # 注册 Hook：通知飞书
        self.register_instance_hook(
            hook_type="pre_acting",
            hook_name="notify_lark",
            hook=self._hook_notify_tool_execution
        )

    def _hook_notify_tool_execution(self, agent_instance, msg, *args):
        """[Hook] 推送工具调用状态"""

        def safe_get(data, key):
            if isinstance(data, dict): return data.get(key)
            return getattr(data, key, None)

        tool_name = None
        inner_call = safe_get(msg, 'tool_call')
        if inner_call:
            tool_name = safe_get(inner_call, 'name') or safe_get(safe_get(inner_call, 'function'), 'name')

        if not tool_name:
            tool_calls = safe_get(msg, 'tool_calls')
            if tool_calls and len(tool_calls) > 0:
                tool_name = safe_get(tool_calls[0], 'name')

        if tool_name and self.manager and self.current_chat_id:
            try:
                # 🔍️ 场景专属 Emoji
                text = f"🔍️️ **Producer Action**: `{tool_name}` ..."
                asyncio.create_task(self.manager.reply(self.current_chat_id, text))
            except Exception as e:
                print(f"⚠️ Hook Error: {e}")

    async def start_service(self, manager: LarkManager):
        """启动监听"""
        print(f"🔍️ [{self.name}] 服务启动...")
        self.manager = manager

        async def _chat_loop(content, sender_id: str, chat_id: str):
            print(f"⚡ [{self.name}] 收到指令 | ChatID: {chat_id}")
            self.current_chat_id = chat_id
            try:
                await manager.reply(chat_id, "✅ 已收到消息")
            except Exception as e:
                print(f"⚠️ Ack Error: {e}")
            model_content, plain_text = normalize_message_content(content)
            msg = Msg(name="user", content=model_content, role="user")
            try:
                response = await self(msg)
                await manager.reply(chat_id, response.content)
            except Exception as e:
                print(f"❌ Error: {e}")
                await manager.reply(chat_id, f"执行出错: {e}")
            finally:
                self.current_chat_id = None

            if any(k in plain_text for k in ["退下", "结束", "再见"]):
                self.memory.clear()
                await manager.reply(chat_id, "✅ 短期记忆已清理。")

        manager.bind_handler(_chat_loop)
        manager.start()

    @classmethod
    def build_from_env(cls) -> Optional[Dict]:
        app_id = os.environ.get("PRODUCE_APP_ID")
        app_secret = os.environ.get("PRODUCE_APP_SECRET")
        bot_name = os.environ.get("PRODUCE_FEISHU_NAME")
        specific_api_key = os.environ.get("PRODUCE_API_KEY")

        if not app_id or not app_secret:
            print("⚠️ [ProduceAgent] 缺少环境变量，跳过。")
            return None

        print("🔍️ [ProduceAgent] 正在组装...")

        # 1. 工具
        note_tool = AgentNotebook(agent_name="ProduceAgent")
        fs_tool = FileTool()
        drive_tool = LarkDriveTool(app_id, app_secret)

        toolkit = Toolkit()
        tools_list = [
            # 读取上游设定
            note_tool.get_scene,
            note_tool.get_character,
            note_tool.get_design_asset,
            note_tool.get_shot,

            # 飞书云盘 (查剧本)
            drive_tool.list_files_in_folder,
            drive_tool.read_document_content,

            # 审核与回填
            note_tool.save_shot,

            # 视觉查看
            fs_tool.read_image_as_url,

            # 备忘
            note_tool.save_memento,
        ]
        for t in tools_list: toolkit.register_tool_function(t)

        register_agent_skills(toolkit, ["skills/film_notebook", "skills/memory_notebook", "skills/drive_lark"])

        # 2. 记忆
        dashscope_key = os.environ.get("EMBEDDING_API_KEY")
        embedding_model = DashScopeTextEmbedding(model_name="text-embedding-v2", api_key=dashscope_key)

        # 记忆LLM配置
        llm_config = load_model_config("gemini_config", override_api_key=specific_api_key)
        llm_config.pop("config_name", None)
        mem0_llm = GeminiChatModel(**llm_config)

        db_path = "/app/data/mem0_produce_db"
        if not os.path.exists(db_path): os.makedirs(db_path, exist_ok=True)

        vector_config = VectorStoreConfig(provider="qdrant", config={"path": db_path})

        memory = Mem0LongTermMemory(
            agent_name="ProduceAgent",
            user_name="User",
            model=mem0_llm,
            embedding_model=embedding_model,
            vector_store_config=vector_config
        )

        note_tool.set_long_term_memory(memory)

        agent = cls(name="ProduceAgent", toolkit=toolkit, memory=memory, api_key=specific_api_key)
        manager = LarkManager(app_id, app_secret, bot_name=bot_name)

        return {"name": "ProduceAgent", "agent": agent, "manager": manager}