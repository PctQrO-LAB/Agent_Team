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


# 假设你已经创建了 GenerationTool，如果还没有，请确保创建该文件
try:
    from src.tools.generate_tools import GenerationTool
except ImportError:
    GenerationTool = None

# ✨ 引用最新的视觉设计 Prompt
from src.config.prompts import DESIGN_SYSTEM_PROMPT
from src.utils.message_utils import normalize_message_content

try:
    from mem0.configs.base import VectorStoreConfig
except ImportError:
    pass


class DesignAgent(ReActAgent):
    """
    [视觉设计总监] (Visual Design Director)
    职责：统一负责角色 (Casting) 和美术 (Design) 的设计、委托生产与资产归档。
    """

    def __init__(self, name: str, toolkit: Toolkit, memory: Mem0LongTermMemory, sys_prompt: str = "",
                 api_key: str = None):
        # 1. 加载模型 (保留 Qwen3-VL 或 DeepSeek，视配置而定)
        # 设计类 Agent 建议使用具备强逻辑或多模态能力的模型
        config_args = load_model_config("qwen3-vl_config", override_api_key=api_key)
        config_args.pop("config_name", None)
        model_instance = DashScopeChatModel(**config_args)

        # ✨ 使用统一的视觉设计 System Prompt
        sys_prompt = DESIGN_SYSTEM_PROMPT

        super().__init__(
            name=name,
            sys_prompt=sys_prompt,
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
                # 🎨 设计专属 Emoji
                text = f"🎨 **Design Action**: `{tool_name}` ..."
                asyncio.create_task(self.manager.reply(self.current_chat_id, text))
            except Exception as e:
                print(f"⚠️ Hook Error: {e}")

    async def start_service(self, manager: LarkManager):
        print(f"🎨 [{self.name}] 视觉设计服务启动...")
        self.manager = manager

        async def _chat_loop(content, sender_id: str, chat_id: str):
            print(f"⚡ [{self.name}] 收到设计指令 | ChatID: {chat_id}")
            self.current_chat_id = chat_id
            try:
                await manager.reply(chat_id, "✅ 已收到消息")
            except Exception as e:
                print(f"⚠️ Ack Error: {e}")

            # 可以在这里注入 Project 上下文，如果 manager 能传递的话
            # content = f"[Context: Project=Default] {text}"

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

            if any(k in plain_text for k in ["没事了", "结束", "再见"]):
                self.memory.clear()
                await manager.reply(chat_id, "✅ 短期记忆已清理。")

        manager.bind_handler(_chat_loop)
        manager.start()

    @classmethod
    def build_from_env(cls) -> Optional[Dict]:
        # ✨ 环境变量前缀变更为 DESIGN_
        app_id = os.environ.get("DESIGN_APP_ID")
        app_secret = os.environ.get("DESIGN_APP_SECRET")
        bot_name = os.environ.get("DESIGN_FEISHU_NAME", "Design Bot")
        specific_api_key = os.environ.get("DESIGN_API_KEY")

        if not app_id or not app_secret:
            print("⚠️ [VisualDesignAgent] 缺少环境变量 (DESIGN_APP_ID/SECRET)，跳过。")
            return None

        print("🎨 [VisualDesignAgent] 正在组装...")

        # 初始化工具实例
        note_tool = AgentNotebook(agent_name="DesignAgent")
        fs_tool = FileTool()
        gen_tool = GenerationTool() if GenerationTool else None

        toolkit = Toolkit()

        # ✨ 注册关键工具：统一的 Design 结构与生成工具
        tools_list = [
            # 1. 筑巢 (Init)
            fs_tool.init_design_structure,
            # 2. 登记/回填 (Register/Backfill)
            note_tool.save_design_asset,
            # 4. 查阅 (Query)
            note_tool.get_design_asset,
            note_tool.save_memento,
            # 视觉感知 (用于看参考图)
            fs_tool.read_image_as_url,
        ]

        # ✨ 5. 委托生成 (Delegate) - 只注册一次
        if gen_tool:
            tools_list.append(gen_tool.generate_image)
        else:
            print("⚠️ Warning: GenerationTool not found. Agent cannot delegate image generation.")

        for t in tools_list: toolkit.register_tool_function(t)

        register_agent_skills(toolkit, [
            "skills/film_notebook",
            "skills/memory_notebook",
            "skills/file_tools",
            "skills/generate_tools"
        ])

        # Embedding & LLM Setup
        dashscope_key = os.environ.get("EMBEDDING_API_KEY")
        embedding_model = DashScopeTextEmbedding(model_name="text-embedding-v2", api_key=dashscope_key)

        llm_config = load_model_config("qwen3-vl_config", override_api_key=specific_api_key)
        llm_config.pop("config_name", None)
        mem0_llm = DashScopeChatModel(**llm_config)

        # ✨ 独立的 Memory 路径
        db_path = "/app/data/mem0_design_db"
        if not os.path.exists(db_path): os.makedirs(db_path, exist_ok=True)

        vector_config = VectorStoreConfig(provider="qdrant", config={"path": db_path})

        memory = Mem0LongTermMemory(
            agent_name="DesignAgent",
            user_name="User",
            model=mem0_llm,
            embedding_model=embedding_model,
            vector_store_config=vector_config
        )

        note_tool.set_long_term_memory(memory)

        agent = cls(name="DesignAgent", toolkit=toolkit, memory=memory, api_key=specific_api_key)
        manager = LarkManager(app_id, app_secret, bot_name=bot_name)

        return {"name": "DesignAgent", "agent": agent, "manager": manager}