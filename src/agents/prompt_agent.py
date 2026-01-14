import asyncio
import os
from typing import Optional, Dict

# AgentScope
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.model import OpenAIChatModel
from agentscope.memory import InMemoryMemory, Mem0LongTermMemory
from agentscope.embedding import DashScopeTextEmbedding
from agentscope.formatter import DeepSeekChatFormatter
from agentscope.message import Msg

# 工具集 (注意文件名是 lark_message_tools)
from src.tools.lark_message_tools import LarkMessageTool
from src.tools.note_tools import AgentNotebook
from src.config.prompts import PROMPT_SYSTEM_PROMPT
from src.tools.file_tools import FileTool
from src.core.load_model import load_model_config
from src.core.lark_manager import LarkManager  # 用于 build_from_env

try:
        from mem0.configs.base import VectorStoreConfig
        from mem0.configs.vector_stores.qdrant import QdrantConfig
except ImportError:
    print("❌ 严重错误: 无法导入 mem0 配置类，请检查依赖安装")



class PromptAgent(ReActAgent):
    def __init__(self, name: str, toolkit: Toolkit, memory: Mem0LongTermMemory, sys_prompt: str = None):
        # 1. 加载模型 (这里我们复用 DeepSeek 作为“大脑”来思考逻辑)
        # 视觉模型只在 "Visual Model" 内部调用，ReAct 逻辑还是用文本模型更强
        config_args = load_model_config("deepseek_config")
        config_args.pop("config_name", None)
        model_instance = OpenAIChatModel(**config_args)

        use_prompt = sys_prompt if sys_prompt else PROMPT_SYSTEM_PROMPT

        super().__init__(
            name=name,
            sys_prompt=use_prompt,
            model=model_instance,
            formatter=DeepSeekChatFormatter(),
            toolkit=toolkit,
            memory=InMemoryMemory(),
            long_term_memory=memory,  # 🔥 继承长期记忆
            long_term_memory_mode="both",
            max_iters=15,
        )

        # 上下文容器
        self.manager: Optional[LarkManager] = None
        self.current_chat_id: Optional[str] = None

        # 🔥 注册钩子：实现工具调用时发送飞书通知
        self.register_instance_hook(
            hook_type="pre_acting",
            hook_name="notify_lark_on_tool_call",
            hook=self._hook_notify_tool_execution
        )

    # === 复用 ScheduleAgent 的钩子逻辑 ===
    def _hook_notify_tool_execution(self, agent_instance, msg, *args):
        """[前端同步版] 嗅探工具调用，并直接推送到飞书"""

        def safe_get(data, key):
            if isinstance(data, dict): return data.get(key)
            return getattr(data, key, None)

        tool_name = "Unknown Tool"
        found = False

        # 1. 嗅探逻辑
        inner_call = safe_get(msg, 'tool_call')
        if inner_call:
            name = safe_get(inner_call, 'name')
            if not name:
                func = safe_get(inner_call, 'function')
                if func: name = safe_get(func, 'name')
            if name:
                tool_name = name
                found = True

        if not found:
            tool_calls = safe_get(msg, 'tool_calls')
            if tool_calls:
                try:
                    first = tool_calls[0]
                    name = safe_get(first, 'name')
                    if name:
                        tool_name = name
                        found = True
                except:
                    pass

        # 2. 推送逻辑
        if found and hasattr(self, "manager") and self.current_chat_id:
            try:
                # 🎨 加个美术总监专属 Emoji
                notification_text = f"🎨 **Prompter Action**: `{tool_name}` ..."
                asyncio.create_task(
                    self.manager.reply(self.current_chat_id, notification_text)
                )
            except Exception as e:
                print(f"⚠️ [Hook] 推送失败: {e}")

    async def start_service(self, manager: LarkManager):
        """启动服务监听"""
        print(f"🎨 [{self.name}] 正在初始化服务...")
        self.manager = manager

        async def _chat_loop(text: str, sender_id: str, chat_id: str):
            print(f"⚡ [{self.name}] 收到视觉需求 | User: {sender_id}")

            # 每次对话前，设置上下文 ID，以便 Hook 能发消息
            self.current_chat_id = chat_id
            msg = Msg(name="user", content=text, role="user")

            try:
                response = await self(msg)
                await manager.reply(chat_id, response.content)
            except Exception as e:
                print(f"❌ Error: {e}")
                await manager.reply(chat_id, f"视觉服务出错: {e}")
            finally:
                self.current_chat_id = None  # 清理上下文

        manager.bind_handler(_chat_loop)
        # 注意：PromptAgent 拥有独立的 Manager，所以必须自己 start
        manager.start()
        print(f"✅ [{self.name}] 服务已就绪 (独立端口)。")

    @classmethod
    def build_from_env(cls) -> Optional[Dict]:
        """工厂方法"""
        # 🔥 读取新的环境变量 (对应你新建立的机器人)
        # 请确保 .env 里加了这两个 Key
        app_id = os.environ.get("PROMPTER_APP_ID")
        app_secret = os.environ.get("PROMPTER_APP_SECRET")
        feishu_name = os.environ.get("PROMPTER_FEISHU_NAME")

        if not app_id or not app_secret:
            print("⚠️ [PromptAgent] 缺少 PROMPTER_APP_ID/SECRET，跳过初始化。")
            return None

        print("🎨 [PromptAgent] 正在组装美术总监...")

        # 1. 初始化工具集
        toolkit = Toolkit()

        # A. 视觉工具 (用新机器人的 ID)
        msg_tool = LarkMessageTool(app_id, app_secret)

        # B. 笔记本与文件工具
        note_tool = AgentNotebook(agent_name="PromptAgent")
        fs_tool = FileTool()

        # C. 注册工具
        tools_list = [
            msg_tool.download_image,  # 核心视觉入口
            note_tool.get_prompt_template,
            note_tool.get_latest_version,  # 👈 刚才修复的那个方法
            note_tool.register_asset,
            note_tool.read_note,  # 允许它读笔记本
            note_tool.save_memento,  # 允许它写长期记忆
            fs_tool.init_shot_structure,
            fs_tool.save_prompt_file
        ]
        for t in tools_list:
            toolkit.register_tool_function(t)

        # 2. 初始化长期记忆 (Mem0)
        # 这里的 user_name 可以写 "DirectorUser" 或者统一 "User"
        dashscope_key = os.environ.get("DASHSCOPE_API_KEY")
        embedding_model = DashScopeTextEmbedding(model_name="text-embedding-v2", api_key=dashscope_key)

        # 记忆的大脑 (DeepSeek)
        llm_config = load_model_config("deepseek_config")
        llm_config.pop("config_name", None)
        mem0_llm = OpenAIChatModel(**llm_config)

        prompter_db_path = "/app/data/mem0_prompter_db"
        if not os.path.exists(prompter_db_path):
            os.makedirs(prompter_db_path, exist_ok=True)

        vector_config_obj = VectorStoreConfig(
            provider="qdrant",
            config={
                "path": prompter_db_path
            }
        )

        memory = Mem0LongTermMemory(
            agent_name="PromptAgent",
            user_name="User",
            model=mem0_llm,
            embedding_model=embedding_model,
            vector_store_config=vector_config_obj  # 👈 传入对象
        )

        # 3. 加载视觉模型配置 (针对 Agent 自身的 VLM 能力)
        # 🔥 关键修改：直接加载你现有的 qwen3-vl_config
        try:
            # 这里填你上传的那个 json 文件里的 config_name
            # 你的文件里写的是 "qwen3-vl_config"
            vlm_config = load_model_config("qwen3-vl_config")

            # ⚠️ 如果 qwen3-vl_config 里写了 app_id/secret，AgentScope 可能会报参数多余
            # 我们清理一下，只留 OpenAIChatModel 需要的参数
            clean_config = {
                "model_name": vlm_config.get("model_name"),
                "api_key": vlm_config.get("api_key"),
                "client_kwargs": vlm_config.get("client_kwargs", {}),
                "generate_args": vlm_config.get("generate_args", {})
            }
            # 注意：OpenAIChatModel 其实主要负责文本对话
            # 这里的 model 传递给 PromptAgent 主要用于 ReAct 思考。
            # 真正的“看图”动作，目前你是通过 download_image 拿到 Base64，
            # 然后需要一个能理解 Image Message 的模型。

            # AgentScope 的 OpenAIChatModel 支持传入多模态消息。
            # 只要 Qwen-VL 兼容 OpenAI 格式接口即可。

        except Exception as e:
            print(f"⚠️ 视觉模型配置加载警告: {e}，将使用 DeepSeek 代替 (可能无法识图)")
            # 兜底
            clean_config = llm_config

        # 4. 实例化
        # 注意：这里我们还是用 deepseek 做 ReAct 的主脑（因为逻辑强）
        # 如果你想让 Qwen-VL 做主脑，可以把 model=... 换成 qwen_model
        # 但通常建议：ReAct 思考用强文本模型，看图时再调 VLM。
        # 鉴于 AgentScope 目前的实现，我们先用 DeepSeek 初始化 Agent

        agent = cls(name="PromptAgent", toolkit=toolkit, memory=memory)

        # 5. 独立的 Manager
        manager_instance = LarkManager(app_id, app_secret, bot_name=feishu_name)

        return {"name": "PromptAgent", "agent": agent, "manager": manager_instance}