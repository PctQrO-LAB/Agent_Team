import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

# 添加项目根目录到 Python 路径，这样 'from src.xxx' 的导入才能工作
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 0. Apply Patches
from src.core.patch import apply_patches
apply_patches()

from agents.schedule_agent import ScheduleAgent

from core.webhook_server import build_webhook_app, start_webhook_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("AssistantLauncher")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
local_env_path = os.path.join(ROOT_DIR, '.env')

if os.path.exists(local_env_path):
    load_dotenv(local_env_path)
    logger.info(f"📂 已加载本地配置文件: {local_env_path}")
else:
    logger.info("🚀 未找到本地 .env 文件，将使用系统/Docker环境变量启动。")

async def main():
    logger.info("🔥 正在唤醒 Assistant Team (Personal Assistant & Schedule)...")

    services = []

    # 1. 尝试组装 Scheduler
    sched_pack = ScheduleAgent.build_from_env()
    if sched_pack:
        services.append(sched_pack)

    # 3. Webhook 服务启动
    webhook_enabled = os.environ.get("WEBHOOK_ENABLED", "1") == "1"
    if webhook_enabled:
        os.environ.setdefault("LARK_EVENT_MODE", "webhook")
        webhook_host = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
        webhook_port = int(os.environ.get("WEBHOOK_PORT", "8000"))
        main_loop = asyncio.get_running_loop()
        
        global_verification_token = os.environ.get("FEISHU_VERIFICATION_TOKEN")

        prefix_map = {
            "Scheduler": "SCHEDULER",
            }

        endpoint_map = {}
        for svc in services:
            name = svc["name"]
            manager = svc["manager"]
            prefix = prefix_map.get(name, name.upper())

            default_endpoint = prefix.lower()
            endpoint = os.environ.get(f"{prefix}_WEBHOOK_PATH") or default_endpoint
            endpoint = endpoint.strip("/")

            verification_token = os.environ.get(f"{prefix}_VERIFICATION_TOKEN") or global_verification_token
            encrypt_key = os.environ.get(f"{prefix}_ENCRYPT_KEY")
            
            logger.info(f"🔐 {name} 使用 Verification Token: {verification_token[:10]}..." if verification_token else f"⚠️ {name} 未配置 Verification Token")

            from core.webhook_server import WebhookEndpointConfig
            endpoint_map[endpoint] = WebhookEndpointConfig(
                manager=manager,
                verification_token=verification_token,
                encrypt_key=encrypt_key,
                event_loop=main_loop,
            )

        app = build_webhook_app(endpoint_map)
        start_webhook_server(app, webhook_host, webhook_port)
        logger.info(f"🌐 Assistant Webhook 服务已启动: http://{webhook_host}:{webhook_port}/{{endpoint}}")

    # 4. 批量点火
    tasks = []
    for svc in services:
        agent = svc["agent"]
        manager = svc["manager"]
        tasks.append(agent.start_service(manager))

    if tasks:
        await asyncio.gather(*tasks)

    logger.info("🌈 Assistant Team 已接管连接。")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass