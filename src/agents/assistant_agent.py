import asyncio
import os
from typing import Optional, Dict

from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.model import DashScopeChatModel
from agentscope.memory import InMemoryMemory, Mem0LongTermMemory
from agentscope.embedding import DashScopeTextEmbedding
from agentscope.formatter import DashScopeChatFormatter
from agentscope.message import Msg

from src.core.load_model import load_model_config
from src.core.lark_manager import LarkManager
from src.core.skill_loader import register_agent_skills
from src.tools.note_tools import AgentNotebook
from src.tools.file_tools import FileTool
from src.tools.lark_drive_tools import LarkDriveTool

from src.config.prompts import ASSISTANT_SYSTEM_PROMPT
from src.utils.message_utils import normalize_message_content

try:
    from mem0.configs.base import VectorStoreConfig
except ImportError:
    pass


class AssistantAgent(ReActAgent):
    """
    [制作助理]
    职责：负责提示词撰写 (Prompt Writing) 和 分镜本地存储 (Local Storage)。
    """

    def __init__(self, name: str, toolkit: Toolkit, memory: Mem0LongTermMemory, sys_prompt: str = "", api_key: str = None):
        # 1. 加载模型 (通常使用文本能力强的模型，如 Qwen-Max 或 DeepSeek，配置里复用 qwen3-vl_config 即可，或者 specialized config)
        config_args = load_model_config("qwen3-vl_config", override_api_key=api_key)
        config_args.pop("config_name", None)
        model_instance = DashScopeChatModel(**config_args)
        
        use_prompt = sys_prompt if sys_prompt else ASSISTANT_SYSTEM_PROMPT

        super().__init__(
            name=name,
            sys_prompt=use_prompt,
            model=model_instance,
            formatter=DashScopeChatFormatter(),
            toolkit=toolkit,
            memory=InMemoryMemory(),
            long_term_memory=None,
            long_term_memory_mode="agent_control",
            max_iters=15,
        )

        self.manager: Optional[LarkManager] = None
        self.current_chat_id: Optional[str] = None

        self.register_instance_hook(
            hook_type="pre_acting",
            hook_name="notify_lark",
            hook=self._hook_notify_tool_execution
        )

    def _hook_notify_tool_execution(self, agent_instance, msg, *args):
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
                # 🛠️ 助理专属 Emoji
                text = f"🛠️ **Assistant Action**: `{tool_name}` ..."
                asyncio.create_task(self.manager.reply(self.current_chat_id, text))
            except Exception as e:
                print(f"⚠️ Hook Error: {e}")

    async def start_service(self, manager: LarkManager):
        print(f"🛠️ [{self.name}] 服务启动...")
        self.manager = manager

        async def _chat_loop(content, sender_id: str, chat_id: str):
            print(f"⚡ [{self.name}] 收到任务 | ChatID: {chat_id}")
            self.current_chat_id = chat_id
            try:
                await manager.reply(chat_id, "✅ 收到任务，开始处理...")
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
        # 优先使用 ASSISTANT 配置，如果不存在则回退到 STORYBOARD 配置
        app_id = os.environ.get("ASSISTANT_APP_ID") or os.environ.get("STORYBOARD_APP_ID")
        app_secret = os.environ.get("ASSISTANT_APP_SECRET") or os.environ.get("STORYBOARD_APP_SECRET")
        bot_name = os.environ.get("ASSISTANT_FEISHU_NAME", "Assistant Bot")
        specific_api_key = os.environ.get("ASSISTANT_API_KEY")

        if not app_id or not app_secret:
            print("⚠️ [AssistantAgent] 缺少环境变量 (ASSISTANT_APP_ID/SECRET)，跳过。")
            return None

        print("🛠️ [AssistantAgent] 正在组装...")

        note_tool = AgentNotebook(agent_name="AssistantAgent")
        fs_tool = FileTool()
        drive_tool = LarkDriveTool(app_id, app_secret)

        toolkit = Toolkit()
        tools_list = [
            # 核心职责：本地存储
            fs_tool.init_shot_structure,  # 建分镜目录
            note_tool.save_shot,          # 存镜头 (含prompt)
            note_tool.get_shot,           # 读镜头
            note_tool.save_beat,          # 存节拍清单
            note_tool.get_beat_list,      # 读节拍清单

            # 飞书云盘
            drive_tool.list_files_in_folder,  # List files
            drive_tool.read_document_content, # Read doc content

            # 辅助
            note_tool.save_memento,
            note_tool.get_latest_version,
            fs_tool.read_image_as_url,
        ]
        for t in tools_list: toolkit.register_tool_function(t)

        register_agent_skills(toolkit, [
            "skills/film_notebook",
            "skills/memory_notebook",
            "skills/file_tools",
            "skills/drive_lark",
            # "skills/generate_tools" # Unlink generate tools as per request to focus on storage/prompt
        ])

        dashscope_key = os.environ.get("EMBEDDING_API_KEY")
        embedding_model = DashScopeTextEmbedding(model_name="text-embedding-v2", api_key=dashscope_key)

        llm_config = load_model_config("qwen3-vl_config", override_api_key=specific_api_key)
        llm_config.pop("config_name", None)
        mem0_llm = DashScopeChatModel(**llm_config)

        # 独立的 Memory 路径
        db_path = "/app/data/mem0_assistant_db"
        if not os.path.exists(db_path): os.makedirs(db_path, exist_ok=True)

        vector_config = VectorStoreConfig(provider="qdrant", config={"path": db_path})

        memory = Mem0LongTermMemory(
            agent_name="AssistantAgent",
            user_name="User",
            model=mem0_llm,
            embedding_model=embedding_model,
            vector_store_config=vector_config
        )

        note_tool.set_long_term_memory(memory)

        agent = cls(name="AssistantAgent", toolkit=toolkit, memory=memory, api_key=specific_api_key)
        manager = LarkManager(app_id, app_secret, bot_name=bot_name)

        return {"name": "AssistantAgent", "agent": agent, "manager": manager}
