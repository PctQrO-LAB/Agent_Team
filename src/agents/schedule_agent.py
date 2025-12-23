# src/agents/schedule_agent.py
import sys
import os

from agentscope.formatter import DeepSeekChatFormatter

# 路径修复
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit  # 导入 Toolkit 类
from src.core.load_model import load_model_config
from src.config.prompts import SCHEDULE_SYSTEM_PROMPT
# 🔥 关键：导入模型和格式化器
# 注意：这里假设你使用的是兼容 OpenAI 接口的模型（DeepSeek 通常兼容）
# 如果你的环境里 model_config 已经配置好了，通常用 load_model_by_config_name 更方便
from agentscope.model import OpenAIChatModel

# 导入工具函数
from src.tools.google_task_tools import (
    get_calendar_events,
    get_google_tasks,
    add_google_task,
    add_calendar_event,
    delete_calendar_event,
    delete_google_task,
)
from src.tools.note_tools import AgentNotebook

class ScheduleAgent(ReActAgent):

    def __init__(self, model_config_name="deepseek_config", name: str = "Scheduler"):
        # === 准备 Model (核心组件) ===
        # ReActAgent 需要一个实体的 model 对象，而不是字符串名字
        # 我们使用 AgentScope 的加载器根据配置名加载模型实例
        config_args = load_model_config("deepseek_config")

        # 1. 初始化属于自己的笔记本
        self.notebook = AgentNotebook("Scheduler")

        # 清理参数：OpenAIChatModel 初始化不需要 config_name，传进去会报 Warning
        model_name_log = config_args.pop("config_name", "unknown")

        # 实例化模型 (使用 OpenAIChatModel)
        print(f"🏭 正在连接模型: {config_args.get('model_name')} (Config: {model_name_log})")

        # 源码中 OpenAIChatModel.__init__ 接受:
        # model_name, api_key, stream, client_kwargs, generate_kwargs ...
        # 我们的 config_args 正好对应这些 keys
        model_instance = OpenAIChatModel(**config_args)

        # 组装工具箱
        my_toolkit = Toolkit()
        tools_list = [
            self.notebook.read_notes,
            self.notebook.write_note,
            self.notebook.delete_note,
            self.notebook.record_created_task,
            get_calendar_events, get_google_tasks,
            add_calendar_event, delete_calendar_event,
            delete_google_task, add_google_task,
        ]
        for tool in tools_list:
            my_toolkit.register_tool_function(tool)


        # === 4. 调用父类构造函数 ===
        # 必须严格对应 agent/_react_agent.py 的 __init__ 参数
        super().__init__(
            name = name,
            sys_prompt = SCHEDULE_SYSTEM_PROMPT,
            model = model_instance,  # 传对象
            formatter = DeepSeekChatFormatter(),  # 传对象
            toolkit = my_toolkit,  # 传对象
            max_iters=30,  # 防止死循环
        )
