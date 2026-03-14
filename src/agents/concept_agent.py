import asyncio
import os
from typing import Optional, Dict

# AgentScope
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.model import OpenAIChatModel
from agentscope.memory import InMemoryMemory, Mem0LongTermMemory
from agentscope.embedding import DashScopeTextEmbedding
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg
from agentscope.plan import PlanNotebook

# Core & Tools
from src.core.load_model import load_model_config
from src.core.lark_manager import LarkManager
from src.core.skill_loader import register_agent_skills
from src.tools.note_tools import AgentNotebook
from src.tools.file_tools import FileTool
from src.tools.lark_message_tools import LarkMessageTool
from src.tools.generate_tools import GenerationTool

from src.config.prompts import CONCEPT_SYSTEM_PROMPT
from src.utils.message_utils import normalize_message_content

try:
    from mem0.configs.base import VectorStoreConfig
except ImportError:
    pass


class ConceptAgent(ReActAgent):
    """
    [场景美术指导]
    职责：负责场景的概念设计、环境图生成和世界观设定。
    """

    def __init__(self, name: str, toolkit: Toolkit, memory: Mem0LongTermMemory, sys_prompt: str = "", api_key: str = None):
        # 1. 加载模型 (doubao-seed_config)
        config_args = load_model_config("doubao-seed_config", override_api_key=api_key)
        config_args.pop("config_name", None)
        model_instance = OpenAIChatModel(**config_args)
        sys_prompt = CONCEPT_SYSTEM_PROMPT
        plan_notebook = PlanNotebook()

        super().__init__(
            name=name,
            sys_prompt=sys_prompt,
            model=model_instance,
            formatter=OpenAIChatFormatter(),
            toolkit=toolkit,
            memory=InMemoryMemory(),
            long_term_memory=None,
            long_term_memory_mode="agent_control",
            max_iters=8,
            plan_notebook=plan_notebook,
        )

        self.manager: Optional[LarkManager] = None
        self.current_chat_id: Optional[str] = None
        self.plan_notebook = plan_notebook

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
                # 🏛️ 场景专属 Emoji
                text = f"🏛️ **Concept Action**: `{tool_name}` ..."
                asyncio.create_task(self.manager.reply(self.current_chat_id, text))
            except Exception as e:
                print(f"⚠️ Hook Error: {e}")

    async def start_service(self, manager: LarkManager):
        """启动监听"""
        print(f"🏛️ [{self.name}] 服务启动...")
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
        app_id = os.environ.get("CONCEPT_APP_ID")
        app_secret = os.environ.get("CONCEPT_APP_SECRET")
        bot_name = os.environ.get("CONCEPT_FEISHU_NAME")
        specific_api_key = os.environ.get("CONCEPT_API_KEY")

        if not app_id or not app_secret:
            print("⚠️ [ConceptAgent] 缺少环境变量，跳过。")
            return None

        print("🏛️ [ConceptAgent] 正在组装...")

        # 1. 工具
        note_tool = AgentNotebook(agent_name="ConceptAgent")
        fs_tool = FileTool()
        gen_tool = GenerationTool()

        toolkit = Toolkit()
        tools_list = [
            fs_tool.init_scene_structure,  # 建场
            note_tool.save_scene,  # 存设定
            note_tool.get_scene,  # 查设定
            fs_tool.read_image_as_url,  # 看本地参考图
            note_tool.save_memento,
            gen_tool.generate_image  # 生图
        ]
        for t in tools_list: toolkit.register_tool_function(t)

        register_agent_skills(toolkit, [
            "skills/film_notebook",
            "skills/memory_notebook",
            "skills/plan_notebook",
            "skills/file_tools",
            "skills/generate_tools"
        ])

        # 2. 记忆
        dashscope_key = os.environ.get("EMBEDDING_API_KEY")
        embedding_model = DashScopeTextEmbedding(model_name="text-embedding-v2", api_key=dashscope_key)

        # 记忆LLM配置
        llm_config = load_model_config("doubao-seed_config", override_api_key=specific_api_key)
        llm_config.pop("config_name", None)
        mem0_llm = OpenAIChatModel(**llm_config)

        db_path = "/app/data/mem0_concept_db"
        if not os.path.exists(db_path): os.makedirs(db_path, exist_ok=True)

        vector_config = VectorStoreConfig(provider="qdrant", config={"path": db_path})

        memory = Mem0LongTermMemory(
            agent_name="ConceptAgent",
            user_name="User",
            model=mem0_llm,
            embedding_model=embedding_model,
            vector_store_config=vector_config
        )

        note_tool.set_long_term_memory(memory)

        agent = cls(name="ConceptAgent", toolkit=toolkit, memory=memory, api_key=specific_api_key)
        manager = LarkManager(app_id, app_secret, bot_name=bot_name)

        return {"name": "ConceptAgent", "agent": agent, "manager": manager}