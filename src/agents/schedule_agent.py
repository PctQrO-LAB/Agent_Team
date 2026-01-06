import os
from typing import Optional, Dict
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- AgentScope ---
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.model import OpenAIChatModel
from agentscope.memory import InMemoryMemory, Mem0LongTermMemory
from agentscope.embedding import DashScopeTextEmbedding
from agentscope.formatter import DeepSeekChatFormatter

# --- 项目模块 ---
from src.core.load_model import load_model_config
from src.config.prompts import SCHEDULE_SYSTEM_PROMPT
from src.tools.lark_schedule_tools import LarkScheduleTool
from src.tools.note_tools import AgentNotebook
from src.tools.clock_tool import ClockTool
from src.core.lark_manager import LarkManager
from agentscope.message import Msg


class ScheduleAgent(ReActAgent):
    """
    ScheduleAgent: 负责日程管理的智能体
    """

    def __init__(self, name: str, toolkit: Toolkit, memory: Mem0LongTermMemory, sys_prompt: str = None):
        # 加载模型配置 (DeepSeek)
        config_args = load_model_config("deepseek_config")
        config_args.pop("config_name", None)
        model_instance = OpenAIChatModel(**config_args)
        use_prompt = sys_prompt if sys_prompt else SCHEDULE_SYSTEM_PROMPT

        super().__init__(
            name=name,
            sys_prompt=use_prompt,
            model=model_instance,
            formatter=DeepSeekChatFormatter(),
            toolkit=toolkit,
            memory=InMemoryMemory(),
            long_term_memory=memory,
            long_term_memory_mode="both",
            max_iters=15,
        )

        # [新增] 1. 初始化上下文容器
        self.manager: Optional[LarkManager] = None
        self.current_chat_id: Optional[str] = None

        # [新增] 2. 注册实例级钩子 (Hook)
        # 根据文档，我们在 _acting (行动) 之前拦截，发送通知
        self.register_instance_hook(
            hook_type="pre_acting",
            hook_name="notify_lark_on_tool_call",
            hook=self._hook_notify_tool_execution
        )

    # [新增] 3. 定义钩子函数
    # 钩子签名必须符合: (self, kwargs) -> dict | None

    def _hook_notify_tool_execution(self, agent_instance, msg, *args):
        """
        [前端同步版] 嗅探工具调用，并直接推送到飞书
        """
        import asyncio  # 引入异步库

        # --- 内部小助手：安全取值 ---
        def safe_get(data, key):
            if isinstance(data, dict):
                return data.get(key)
            return getattr(data, key, None)

        tool_name = "Unknown Tool"
        found = False

        # -----------------------------------------------------------
        # 1. 嗅探逻辑 (之前的代码，保持不变)
        # -----------------------------------------------------------
        # 针对 keys=['tool_call'] 的结构提取
        inner_call = safe_get(msg, 'tool_call')
        if inner_call:
            name = safe_get(inner_call, 'name')
            if not name:
                func = safe_get(inner_call, 'function')
                if func: name = safe_get(func, 'name')
            if name:
                tool_name = name
                found = True

        # 兜底：兼容标准 tool_calls
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

        # -----------------------------------------------------------
        # 2. 推送逻辑 (新增部分！)
        # -----------------------------------------------------------
        if found:
            # A. 后台日志 (给程序员看)
            print(f"\n[后台日志] 🛠️ {self.name} 正在调用工具: `{tool_name}` ...")

            # B. 前端通知 (给用户看)
            # 检查1: Manager 是否已注入?
            # 检查2: 当前是否有正在对话的用户 (current_chat_id)?
            if hasattr(self, "manager") and hasattr(self, "current_chat_id") and self.current_chat_id:
                try:
                    notification_text = f"🛠️ **正在调用工具**: `{tool_name}` ..."

                    # 【核心操作】创建一个异步任务去发飞书，不阻塞当前流程
                    # 注意：self.manager.reply 是你提供的 LarkManager 里的那个异步方法
                    asyncio.create_task(
                        self.manager.reply(self.current_chat_id, notification_text)
                    )
                except Exception as e:
                    print(f"⚠️ [Hook] 推送飞书失败: {e}")
            else:
                # 如果没有 chat_id，说明可能是后台自启动任务，或者还没初始化好
                pass


    async def start_service(self, manager: LarkManager):
        """
        [生命周期入口] 开启服务
        """
        print(f"🚀 [{self.name}] 正在初始化服务与生物钟...")

        # [新增] 注入 manager
        self.manager = manager

        user_open_id = os.environ.get("USER_OPEN_ID")

        # -----------------------------------------------------
        # Part A: 配置生物钟 (定时任务)
        # -----------------------------------------------------
        if user_open_id:
            self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

            async def trigger_report(report_type: str, prompt: str):
                print(f"⏰ [{self.name}] 生物钟触发: {report_type}")
                time_content = ClockTool().get_current_datetime().content[0]

                # 兼容处理：如果是对象则用 .text，如果是字典则用 .get("text")
                if isinstance(time_content, dict):
                    current_time_str = time_content.get("text")
                else:
                    current_time_str = time_content.text

                full_prompt = f"【系统时间: {current_time_str}】\n{prompt}"
                msg = Msg(name="system_clock", content=full_prompt, role="user")

                try:
                    # [新增] 设置上下文 ID，让定时任务也能触发钩子通知
                    self.current_chat_id = user_open_id

                    response = await self(msg)
                    await manager.reply(user_open_id, response.content)

                    if report_type == "晚报":
                        self.memory.clear()
                        print(f"🧹 [{self.name}] 晚报结束，短期记忆已清理。")

                except Exception as e:
                    print(f"❌ 定时任务执行失败: {e}")
                finally:
                    # [新增] 清理上下文
                    self.current_chat_id = None

            self.scheduler.add_job(trigger_report, 'cron', hour=8, minute=0, args=["晨报", "[系统指令] 晨报时间。请读取笔记本，审计今日日程，并给出排程建议。"])
            self.scheduler.add_job(trigger_report, 'cron', hour=12, minute=0, args=["午报", "[系统指令] 午报时间。请检查上午完成情况，确认下午安排。"])
            self.scheduler.add_job(trigger_report, 'cron', hour=20, minute=0, args=["晚报", "[系统指令] 晚报时间。请总结全天工作，提取行为规律(add_pattern)，并清理已完成事项。"])

            self.scheduler.start()
            print(f"⏰ [{self.name}] 生物钟已启动")
        else:
            print(f"⚠️ [{self.name}] 未配置 USER_OPEN_ID")

        # -----------------------------------------------------
        # Part B: 配置交互逻辑 (被动响应)
        # -----------------------------------------------------
        async def _chat_loop(text: str, sender_id: str, chat_id: str):
            print(f"⚡ [{self.name}] 收到消息 | User: {sender_id}")

            msg = Msg(name="user", content=text, role="user")
            try:
                # [新增] 设置当前聊天的上下文 ID
                self.current_chat_id = chat_id

                response = await self(msg)
                await manager.reply(chat_id, response.content)
            except Exception as e:
                print(f"❌ 运行报错: {e}")
                await manager.reply(chat_id, f"系统错误: {e}")
            finally:
                # [新增] 清理上下文
                self.current_chat_id = None

            if any(k in text for k in ["退下", "结束", "再见"]):
                self.memory.clear()
                await manager.reply(chat_id, "✅ 短期记忆已清理。")

        manager.bind_handler(_chat_loop)
        manager.start()
        print(f"✅ [{self.name}] 服务全线就绪。")

    @classmethod
    def build_from_env(cls) -> Optional[Dict]:
        """[工厂方法]"""
        app_id = os.environ.get("SCHEDULER_APP_ID")
        app_secret = os.environ.get("SCHEDULER_APP_SECRET")
        user_id = os.environ.get("USER_OPEN_ID")

        if not app_id or not app_secret:
            print("⚠️ [Scheduler] 缺少环境变量配置，跳过初始化。")
            return None

        print(f"🛠️ [ScheduleAgent] 正在自我组装 (Target: {user_id})...")

        lark_tool = LarkScheduleTool(app_id, app_secret, user_id)
        notebook = AgentNotebook(agent_name="Scheduler")
        clock_tool = ClockTool()

        # ----------------------------------------------------
        # 1. 动态生成 Prompt (注入数据库地图)
        # ----------------------------------------------------
        db_schema = notebook.get_schema_prompt()
        full_sys_prompt = SCHEDULE_SYSTEM_PROMPT + "\n" + db_schema

        toolkit = Toolkit()
        tools_list = [
            lark_tool.get_calendar_events, lark_tool.create_calendar_event, lark_tool.delete_calendar_event,
            lark_tool.get_tasks, lark_tool.create_task, lark_tool.delete_task,
            lark_tool.debug_user_identity,
            notebook.read_note, notebook.save_to_note,
            notebook.save_memento, notebook.add_pattern,
            notebook.promote_pattern_to_memory, notebook.update_project_status,
            notebook.query_note, notebook.delete_from_note,
            clock_tool.get_current_datetime,
        ]
        for t in tools_list:
            toolkit.register_tool_function(t)

        dashscope_key = os.environ.get("DASHSCOPE_API_KEY")
        embedding_model = DashScopeTextEmbedding(model_name="text-embedding-v2", api_key=dashscope_key)
        llm_config = load_model_config("deepseek_config")
        llm_config.pop("config_name", None)
        mem0_llm = OpenAIChatModel(**llm_config)

        memory = Mem0LongTermMemory(
            agent_name="Scheduler",
            user_name="User",
            model=mem0_llm,
            embedding_model=embedding_model,
            on_disk=True,
        )

        agent_instance = cls(name="Scheduler", sys_prompt=full_sys_prompt, toolkit=toolkit, memory=memory)
        manager_instance = LarkManager(app_id, app_secret)

        return {"name": "Scheduler", "agent": agent_instance, "manager": manager_instance}