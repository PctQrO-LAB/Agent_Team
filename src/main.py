import asyncio
import os
import datetime
import sys

# 路径修复
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

from agentscope.message import Msg
from src.agents.schedule_agent import ScheduleAgent


async def main_daemon(agent_name: str):
    print(f"\n🤖 === {agent_name} 智能排程 Agent 启动 ===")
    print(f"📂 记忆机制: 纯笔记本模式 (无状态运行)")
    print(f"⏰ 时区设置: UTC+8 (北京时间)")

    # 1. 初始化 Agent
    # 注意：Agent 内部会自动关联 data/notebook_{agent_name}.json
    agent = ScheduleAgent(model_config_name="deepseek_config", name=agent_name)

    while True:
        try:
            # 2. 获取正确的北京时间
            utc_plus_8 = datetime.timezone(datetime.timedelta(hours=8))
            now = datetime.datetime.now(utc_plus_8)
            now_str = now.strftime("%Y-%m-%d %H:%M (%A)")

            # 3. 构造指令：强制要求先"回忆"(翻笔记)
            # 这里的 Prompt 必须强硬，确保它按 SOP 执行
            trigger_content = (
                f"【当前系统时间】: {now_str}\n"
                f"🔴 **立即开始巡检**\n"
                f"请严格基于你 System Prompt 中的 **5步 SOP** 进行操作。\n"
                f"重点检查：是否有新日程需要生成对应的 Google Task 凭证 (Step 4)。\n"
                f"如果没有实际变动，请回复简短总结。"
            )

            trigger_msg = Msg(name="System", role="system", content=trigger_content)

            print(f"\n👀 [{now_str}] 唤醒 Agent 开始巡检...")

            # 4. Agent 开始思考和行动
            await agent.reply(trigger_msg)

            # 5. 🔥 关键修正：干完活就清空短期记忆！
            # 这样保证它下一轮是通过 read_notes 工具来"回忆"，而不是靠缓存的对话历史
            # 同时也彻底解决了 token 无限增长的问题
            await agent.memory.clear()
            # print("🧹 短期记忆已清理，状态已固化到笔记本。")

            # 6. 休息 (例如 5 分钟)
            await asyncio.sleep(600)

        except KeyboardInterrupt:
            print("\n🛑 程序已停止")
            break
        except Exception as e:
            print(f"⚠️ 运行异常: {e}")
            # 出错也要休息，防止死循环刷 API
            await asyncio.sleep(600)


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # 启动
    asyncio.run(main_daemon("Scheduler"))