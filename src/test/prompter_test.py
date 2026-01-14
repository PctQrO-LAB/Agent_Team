import sys
import os
import asyncio
from dotenv import load_dotenv

# 路径修补：确保能找到 src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.agents.prompt_agent import PromptAgent
from agentscope.message import Msg

load_dotenv()


async def test_full_director_workflow():
    print("🎬 Action! 测试美术总监全流程...")

    # 1. 获取 ID (假设你把新机器人的 ID 放在了环境变量或者这里硬编码)
    # 如果你在 .env 里配了 PROMPTER_APP_ID，可以直接用
    # 如果没配，我们在这里临时注入一下，骗过 build_from_env
    APP_ID = os.environ.get("PROMPTER_APP_ID") or os.environ.get("SCHEDULER_APP_ID")
    APP_SECRET = os.environ.get("PROMPTER_APP_SECRET") or os.environ.get("SCHEDULER_APP_SECRET")

    if not APP_ID or not APP_SECRET:
        print("❌ 错误：未找到 APP_ID/SECRET，请检查 .env 文件")
        return

    # 🔥 关键修改：临时设置环境变量，让工厂方法能读取到
    os.environ["PROMPTER_APP_ID"] = APP_ID
    os.environ["PROMPTER_APP_SECRET"] = APP_SECRET

    # 2. 使用工厂方法自动组装 (代替手动 new)
    # build_from_env 会自动创建 Toolkit, Memory, 加载 Config
    package = PromptAgent.build_from_env()

    if not package:
        print("❌ Agent 初始化失败")
        return

    agent = package["agent"]  # 拿到 Agent 实例
    manager = package["manager"]  # 拿到对应的飞书管理器

    # 3. 构造模拟输入
    # ⚠️ 提示：为了测试视觉，最好填入真实的 MessageID (从飞书日志找)，否则只能测文本逻辑
    REAL_MSG_ID = "om_xxxxxxxxxx"
    REAL_IMG_KEY = "img_xxxxxxxxxx"

    user_input = f"""
    [System: User sent an image. MessageID: {REAL_MSG_ID}, ImageKey: {REAL_IMG_KEY}]
    请用 mj 画一张类似的图，赛博朋克风格。
    """

    msg = Msg(name="user", content=user_input, role="user")

    print(f"👤 模拟输入: {user_input}")
    print("🤖 Agent 正在思考 (观察 -> 查模版 -> 存文件 -> 输出)...")

    # 4. 运行 Agent
    # 注意：这里我们没有启动 manager.start()，因为只是单元测试 Agent 的思考逻辑
    # 如果需要测试发飞书消息，可以将 manager 传进去或者 Mock 一下

    # 临时给 agent 注入 manager 以便 Hook 能工作 (可选)
    agent.manager = manager
    agent.current_chat_id = "ou_test_user_id"  # 模拟一个用户ID，让 Hook 能打印日志

    response = await agent(msg)

    print("\n✅ Agent 最终回复:")
    print(response.content)


if __name__ == "__main__":
    # Windows/Mac 兼容性设置
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_full_director_workflow())