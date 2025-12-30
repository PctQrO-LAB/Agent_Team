import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.schedule_agent import ScheduleAgent

# from agents.coder_agent import CoderAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("Launcher")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT_DIR, '.env'))


async def main():
    logger.info("🔥 正在唤醒 Agent Team...")

    services = []

    # 1. 尝试组装 Scheduler
    sched_pack = ScheduleAgent.build_from_env()
    if sched_pack:
        services.append(sched_pack)

    # 2. 尝试组装 Coder
    # coder_pack = CoderAgent.build_from_env()
    # if coder_pack: services.append(coder_pack)

    if not services:
        logger.error("❌ 无可用 Agent。")
        return

    # 3. 批量点火
    for svc in services:
        agent = svc["agent"]
        manager = svc["manager"]

        # 🔥 关键点：Launcher 不再管怎么跑，直接调用 Agent 自己的启动方法
        # 这就是你想要的：生命周期模板由 Agent 自己决定
        await agent.start_service(manager)

    # 4. 定时任务 (Scheduler 专属)
    # 如果想把定时任务也封装进 Scheduler，可以在 start_service 里判断是否开启定时器
    # 这里为了演示简单，保留部分外部逻辑，或者你也把它移进去
    # ...

    logger.info("🌈 所有 Agent 已接管连接。")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass