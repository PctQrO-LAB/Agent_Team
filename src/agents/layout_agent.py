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
from agentscope.plan import PlanNotebook

from src.core.load_model import load_model_config
from src.core.lark_manager import LarkManager
from src.core.skill_loader import register_agent_skills
from src.tools.note_tools import AgentNotebook
from src.tools.file_tools import FileTool
from src.tools.generate_tools import GenerationTool
from src.tools.lark_drive_tools import LarkDriveTool

from src.config.prompts import LAYOUT_SYSTEM_PROMPT
from src.utils.message_utils import normalize_message_content

try:
    from mem0.configs.base import VectorStoreConfig
except ImportError:
    pass


class LayoutAgent(ReActAgent):
    """
    [机位与背景美术师]
    职责：阅读分镜剧本归纳机位需求，结合场景概念图生成对应的机位背景图。
    """

    def __init__(self, name: str, toolkit: Toolkit, memory: Mem0LongTermMemory, sys_prompt: str = "", api_key: str = None):
        config_args = load_model_config("gemini_config", override_api_key=api_key)
        config_args.pop("config_name", None)
        model_instance = GeminiChatModel(**config_args)
        sys_prompt = LAYOUT_SYSTEM_PROMPT
        plan_notebook = PlanNotebook()

        super().__init__(
            name=name,
            sys_prompt=sys_prompt,
            model=model_instance,
            formatter=GeminiChatFormatter(),
            toolkit=toolkit,
            memory=memory
        )
        self.current_chat_id = None
        self.toolkit = toolkit
        self.memory = memory

    async def start_service(self, manager: LarkManager):
        print(f"🎬 [LayoutAgent] 正在监听飞书消息 (Bot: {manager.bot_name})...")

        async def _chat_loop(chat_id, content):
            if self.current_chat_id is not None:
                await manager.reply(chat_id, "⚠️ 我正在处理另一个机位绘制任务，请稍等...")
                return

            self.current_chat_id = chat_id
            sys_info = "\n\n【系统提醒】你现在正处于跟用户的对话中。请立刻开始规划如何提取机位与生成背景，并在完成后再向用户报告。"
            if isinstance(content, str):
                content += sys_info
            elif isinstance(content, list) and len(content) > 0 and isinstance(content[0], dict) and "text" in content[0]:
                content[0]["text"] += sys_info

            try:
                await manager.reply(chat_id, "收到分镜处理需求，我正在调取概念图并规划机位视角...")
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
        app_id = os.environ.get("LAYOUT_APP_ID")
        app_secret = os.environ.get("LAYOUT_APP_SECRET")
        bot_name = os.environ.get("LAYOUT_FEISHU_NAME", "Layout Bot")
        specific_api_key = os.environ.get("LAYOUT_API_KEY")

        if not app_id or not app_secret:
            print("⚠️ [LayoutAgent] 缺少环境变量，跳过。")
            return None

        print("🎬 [LayoutAgent] 正在组装...")

        note_tool = AgentNotebook(agent_name="LayoutAgent")
        fs_tool = FileTool()
        gen_tool = GenerationTool()
        drive_tool = LarkDriveTool(app_id, app_secret)

        toolkit = Toolkit()
        tools_list = [
            # 读素材
            note_tool.get_scene,  
            note_tool.get_design_asset,
            note_tool.query_design_assets,
            note_tool.list_shots, # 读分镜

            # 飞书云盘 (查资料)
            drive_tool.list_files_in_folder,
            drive_tool.read_document_content,

            # 生成工具
            gen_tool.generate_image,
            gen_tool.generate_image_batch,
            
            # 存素材 / 笔记
            note_tool.save_design_asset,
            note_tool.save_memento,
            note_tool.get_dashboard,
            fs_tool.read_image_as_url,
        ]
        for t in tools_list: toolkit.register_tool_function(t)

        register_agent_skills(toolkit, [
            "skills/film_notebook",
            "skills/memory_notebook",
            "skills/plan_notebook",
            "skills/file_tools",
            "skills/drive_lark",
            "skills/generate_tools"
        ])

        dashscope_key = os.environ.get("EMBEDDING_API_KEY")
        if dashscope_key:
            embedding_model = DashScopeTextEmbedding(model_name="text-embedding-v2", api_key=dashscope_key)
        else:
            embedding_model = None

        llm_config = load_model_config("gemini_config", override_api_key=specific_api_key)
        llm_config.pop("config_name", None)
        mem0_llm = GeminiChatModel(**llm_config)

        db_path = "/app/data/mem0_layout_db"
        if not os.path.exists(db_path): os.makedirs(db_path, exist_ok=True)

        vector_config = VectorStoreConfig(provider="qdrant", config={"path": db_path})

        memory = Mem0LongTermMemory(
            agent_name="LayoutAgent",
            user_name="User",
            model=mem0_llm,
            embedding_model=embedding_model,
            vector_store_config=vector_config
        )

        note_tool.set_long_term_memory(memory)

        agent = cls(name="LayoutAgent", toolkit=toolkit, memory=memory, api_key=specific_api_key)
        manager = LarkManager(app_id, app_secret, bot_name=bot_name)

        return {"name": "LayoutAgent", "agent": agent, "manager": manager}
