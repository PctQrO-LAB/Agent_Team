import os
import sys
import lark_oapi as lark
from dotenv import load_dotenv

# 加载环境变量
# 假设脚本在 src/test/ 下，.env 在项目根目录
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(current_dir))
load_dotenv(os.path.join(root_dir, ".env"))


def run_keeper(bot_type):
    APP_ID = os.getenv("STORYBOARD_APP_ID")
    APP_SECRET = os.getenv("STORYBOARD_APP_SECRET")

    print(f"🔌 正在连接飞书 (AppID: {APP_ID})...")
    print("⚠️  连接成功后，请立即去飞书后台点击【保存】！")

    # 极简配置，只为保持连接
    event_handler = lark.EventDispatcherHandler.builder("", "").build()

    client = lark.ws.Client(
        APP_ID,
        APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO
    )

    # 启动（阻塞模式，不会崩）
    client.start()


if __name__ == "__main__":
    # 默认跑日程，如果想跑提示词，运行: python src/test/keep_alive.py prompter
    target = sys.argv[1] if len(sys.argv) > 1 else "scheduler"
    run_keeper(target)