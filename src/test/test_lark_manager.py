import os
import sys

# --------------------------------------------------------
# 路径修复（确保能找到 src 模块）
# --------------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(project_root)

# --------------------------------------------------------
# 核心代码
# --------------------------------------------------------
from dotenv import load_dotenv
from src.core.lark_manager import LarkManager
from agentscope.agent import AgentBase
from agentscope.message import Msg

# 加载环境变量
load_dotenv()


# 1. 定义 EchoAgent
class EchoAgent(AgentBase):
    def __init__(self, name: str):
        super().__init__()
        self.name = name

    async def reply(self, x: Msg) -> Msg:
        content = f"【测试成功】我收到了你的消息：{x.content}"
        return Msg(name=self.name, role="assistant", content=content)


# 2. 注意：这里改成了普通函数 def，而不是 async def
def test_main():
    print("🛠️ 开始进行 LarkManager 连通性测试...")

    app_id = os.environ.get("SCHEDULER_APP_ID")
    app_secret = os.environ.get("SCHEDULER_APP_SECRET")

    if not app_id or not app_secret:
        print("❌ 错误：未在环境变量中找到 SCHEDULER_APP_ID 或 SCHEDULER_APP_SECRET")
        return

    # 初始化
    echo_agent = EchoAgent(name="EchoBot")
    manager = LarkManager(app_id, app_secret)

    print("正在连接飞书服务器...")

    # 3. 启动长连接
    # 这个方法是阻塞的，它会自动运行一个事件循环，直到手动停止
    try:
        manager.start()
    except KeyboardInterrupt:
        print("\n🛑 测试已手动停止")


if __name__ == "__main__":
    # 4. 直接调用函数，不要用 asyncio.run()
    test_main()