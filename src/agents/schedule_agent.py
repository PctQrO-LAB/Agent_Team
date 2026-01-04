import sys
import os
from typing import Optional, Dict, List
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
from agentscope.message import Msg # 确保引入了 Msg

class ScheduleAgent(ReActAgent):
    """
    ScheduleAgent: 负责日程管理的智能体
    """

    # 1. __init__ 保持纯净 (依赖注入)，方便未来扩展或测试
    def __init__(self, name: str, toolkit: Toolkit, memory: Mem0LongTermMemory):
        # 加载模型配置 (DeepSeek)
        config_args = load_model_config("deepseek_config")
        config_args.pop("config_name", None)
        model_instance = OpenAIChatModel(**config_args)

        super().__init__(
            name=name,
            sys_prompt=SCHEDULE_SYSTEM_PROMPT,
            model=model_instance,
            formatter=DeepSeekChatFormatter(),
            toolkit=toolkit,
            memory=InMemoryMemory(),
            long_term_memory=memory,
            long_term_memory_mode="both",
            max_iters=15,
        )

    async def start_service(self, manager: LarkManager):
        """
        [生命周期入口] 开启服务：
        1. 启动飞书监听 (被动交互)
        2. 启动生物钟 (主动交互/定时任务)
        """
        print(f"🚀 [{self.name}] 正在初始化服务与生物钟...")

        # 获取老板 ID (用于主动发报)
        user_open_id = os.environ.get("USER_OPEN_ID")

        # -----------------------------------------------------
        # Part A: 配置生物钟 (定时任务)
        # -----------------------------------------------------
        if user_open_id:
            self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

            # 定义主动汇报的逻辑 (闭包)
            async def trigger_report(report_type: str, prompt: str):
                print(f"⏰ [{self.name}] 生物钟触发: {report_type}")
                # 1. 构造系统指令
                current_time_str = ClockTool().get_current_datetime().content[0].text
                full_prompt = f"【系统时间: {current_time_str}】\n{prompt}"
                msg = Msg(name="system_clock", content=full_prompt, role="user")

                try:
                    # 2. 思考
                    response = await self(msg)
                    # 3. 发送给老板 (调用 Manager 的主动发送接口)
                    # 注意：这里需要 Manager 提供主动发送功能，而不是 reply
                    # 我们直接用 manager.reply 传 user_open_id 也可以，或者 manager._send_lark_card
                    # 为了优雅，建议使用 manager.reply(user_open_id, ...)
                    await manager.reply(user_open_id, response.content)

                    # 4. 晚报后的特殊清理
                    if report_type == "晚报":
                        self.memory.clear()
                        print(f"🧹 [{self.name}] 晚报结束，短期记忆已清理。")

                except Exception as e:
                    print(f"❌ 定时任务执行失败: {e}")

            # 添加三报任务
            # 晨报 08:00
            self.scheduler.add_job(trigger_report, 'cron', hour=8, minute=0,
                                   args=["晨报", "[系统指令] 晨报时间。请读取笔记本，审计今日日程，并给出排程建议。"])
            # 午报 12:00
            self.scheduler.add_job(trigger_report, 'cron', hour=12, minute=0,
                                   args=["午报", "[系统指令] 午报时间。请检查上午完成情况，确认下午安排。"])
            # 晚报 20:00
            self.scheduler.add_job(trigger_report, 'cron', hour=20, minute=0,
                                   args=["晚报", "[系统指令] 晚报时间。请总结全天工作，提取行为规律(add_pattern)，并清理已完成事项。"])

            self.scheduler.start()
            print(f"⏰ [{self.name}] 生物钟已启动 (08:00/12:00/20:00)")
        else:
            print(f"⚠️ [{self.name}] 未配置 USER_OPEN_ID，定时任务未启动。")

        # -----------------------------------------------------
        # Part B: 配置交互逻辑 (被动响应)
        # -----------------------------------------------------
        async def _chat_loop(text: str, sender_id: str, chat_id: str):
            print(f"⚡ [{self.name}] 收到消息 | User: {sender_id}")

            msg = Msg(name="user", content=text, role="user")
            try:
                response = await self(msg)
                await manager.reply(chat_id, response.content)
            except Exception as e:
                print(f"❌ 运行报错: {e}")
                await manager.reply(chat_id, f"系统错误: {e}")

            # 退出指令
            if any(k in text for k in ["退下", "结束", "再见"]):
                self.memory.clear()
                await manager.reply(chat_id, "✅ 短期记忆已清理。")

        # 绑定并启动飞书监听
        manager.bind_handler(_chat_loop)
        manager.start()
        print(f"✅ [{self.name}] 服务全线就绪。")


    # 2. 🔥 新增：标准构造方法 (把封装还给你)
    @classmethod
    def build_from_env(cls) -> Optional[Dict]:
        """
        [工厂方法] 从环境变量自动读取配置，组装并返回 Agent 和配套的 Manager。
        Returns:
             { "agent": instance, "manager": manager_instance }
        """
        # 读取配置
        app_id = os.environ.get("SCHEDULER_APP_ID")
        app_secret = os.environ.get("SCHEDULER_APP_SECRET")
        user_id = os.environ.get("USER_OPEN_ID")

        if not app_id or not app_secret:
            print("⚠️ [Scheduler] 缺少环境变量配置，跳过初始化。")
            return None

        print(f"🛠️ [ScheduleAgent] 正在自我组装 (Target: {user_id})...")

        # A. 准备工具
        lark_tool = LarkScheduleTool(app_id, app_secret, user_id)
        notebook = AgentNotebook(agent_name="Scheduler")
        clock_tool = ClockTool()

        toolkit = Toolkit()
        tools_list = [
            lark_tool.get_calendar_events, lark_tool.create_calendar_event, lark_tool.delete_calendar_event,
            lark_tool.get_tasks, lark_tool.create_task, lark_tool.delete_task,
            lark_tool.debug_user_identity,
            notebook.read_notebook, notebook.record_task, notebook.update_task_status,
            notebook.save_memento, notebook.record_calendar_event, notebook.add_pattern,
            notebook.promote_pattern_to_memory, notebook.update_project_status,
            clock_tool.get_current_datetime,
        ]
        for t in tools_list:
            toolkit.register_tool_function(t)

        # B. 准备记忆
        dashscope_key = os.environ.get("DASHSCOPE_API_KEY")
        embedding_model = DashScopeTextEmbedding(
            model_name="text-embedding-v2",
            api_key=dashscope_key
        )
        # 复用模型配置给 Mem0
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

        # C. 实例化自己
        agent_instance = cls(
            name="Scheduler",
            toolkit=toolkit,
            memory=memory
        )

        # D. 实例化连接器
        manager_instance = LarkManager(app_id, app_secret)

        # 打包返回
        return {
            "name": "Scheduler",
            "agent": agent_instance,
            "manager": manager_instance
        }