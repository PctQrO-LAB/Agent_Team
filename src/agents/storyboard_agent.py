import asyncio
import os
from typing import Optional, Dict

from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.model import GeminiChatModel
from agentscope.memory import InMemoryMemory, Mem0LongTermMemory
from agentscope.embedding import DashScopeTextEmbedding
from agentscope.formatter import GeminiChatFormatter
from agentscope.message import Msg

from src.core.load_model import load_model_config
from src.core.lark_manager import LarkManager
from src.core.skill_loader import register_agent_skills
from src.tools.note_tools import AgentNotebook
from src.tools.file_tools import FileTool
from src.tools.generate_tools import GenerationTool
from src.tools.lark_drive_tools import LarkDriveTool

from src.config.prompts import STORYBOARD_SYSTEM_PROMPT
from src.utils.message_utils import normalize_message_content

try:
    from mem0.configs.base import VectorStoreConfig
except ImportError:
    pass


class StoryboardAgent(ReActAgent):
    """
    [电影分镜师]
    职责：负责将场景和人物组装成具体镜头。调用场景和人物的素材，输出分镜画面。
    """

    def __init__(self, name: str, toolkit: Toolkit, memory: Mem0LongTermMemory, sys_prompt: str = "", api_key: str = None):
        # 1. 加载模型 (Gemini)
        config_args = load_model_config("gemini_config", override_api_key=api_key)
        config_args.pop("config_name", None)
        model_instance = GeminiChatModel(**config_args)
        sys_prompt = STORYBOARD_SYSTEM_PROMPT

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
                # 🎥 分镜专属 Emoji
                text = f"🎥 **Storyboard Action**: `{tool_name}` ..."
                asyncio.create_task(self.manager.reply(self.current_chat_id, text))
            except Exception as e:
                print(f"⚠️ Hook Error: {e}")

    async def start_service(self, manager: LarkManager):
        print(f"🎥 [{self.name}] 服务启动...")
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
        app_id = os.environ.get("STORYBOARD_APP_ID")
        app_secret = os.environ.get("STORYBOARD_APP_SECRET")
        bot_name = os.environ.get("STORYBOARD_FEISHU_NAME", "Storyboard Bot")
        specific_api_key = os.environ.get("STORYBOARD_API_KEY")

        if not app_id or not app_secret:
            print("⚠️ [StoryboardAgent] 缺少环境变量，跳过。")
            return None

        print("🎥 [StoryboardAgent] 正在组装...")

        note_tool = AgentNotebook(agent_name="StoryboardAgent")
        fs_tool = FileTool()
        gen_tool = GenerationTool()
        drive_tool = LarkDriveTool(app_id, app_secret)

        toolkit = Toolkit()
        tools_list = [
            # 核心：读素材 (只读不写)
            note_tool.get_scene,  # 读环境
            note_tool.get_design_asset,  # 读人设 (会自动触发OSS桥接)

            # 飞书云盘 (查资料)
            drive_tool.list_files_in_folder,
            drive_tool.read_document_content,

            # 核心：批量写
            note_tool.save_beat_list, # 批量写节拍
            note_tool.save_beat,      # 单个写节拍 (可选)
            note_tool.save_shot_batch, # 批量写镜头
            note_tool.save_shot,       # 单个写镜头

            # 杂项
            note_tool.save_memento,
            note_tool.get_dashboard,
            fs_tool.read_image_as_url,  # 看本地参考图
            gen_tool.generate_storyboard_batch, # 批量生成分镜
        ]
        for t in tools_list: toolkit.register_tool_function(t)

        register_agent_skills(toolkit, [
            "skills/film_notebook",
            "skills/memory_notebook",
            "skills/file_tools",
            "skills/drive_lark",
            "skills/generate_tools"
        ])

        dashscope_key = os.environ.get("EMBEDDING_API_KEY")
        embedding_model = DashScopeTextEmbedding(model_name="text-embedding-v2", api_key=dashscope_key)

        # Mem0 内置模型也跟随主模型切换到 Gemini
        llm_config = load_model_config("gemini_config", override_api_key=specific_api_key)
        llm_config.pop("config_name", None)
        mem0_llm = GeminiChatModel(**llm_config)

        # 独立的 Memory 路径
        db_path = "/app/data/mem0_storyboard_db"
        if not os.path.exists(db_path): os.makedirs(db_path, exist_ok=True)

        vector_config = VectorStoreConfig(provider="qdrant", config={"path": db_path})

        memory = Mem0LongTermMemory(
            agent_name="StoryboardAgent",
            user_name="User",
            model=mem0_llm,
            embedding_model=embedding_model,
            vector_store_config=vector_config
        )

        note_tool.set_long_term_memory(memory)

        agent = cls(name="StoryboardAgent", toolkit=toolkit, memory=memory, api_key=specific_api_key)
        manager = LarkManager(app_id, app_secret, bot_name=bot_name)

        return {"name": "StoryboardAgent", "agent": agent, "manager": manager}