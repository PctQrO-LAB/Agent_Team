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
from agents.concept_agent import ConceptAgent
from agents.storyboard_agent import StoryboardAgent
from agents.produce_agent import ProduceAgent
from agents.design_agent import DesignAgent
from agents.assistant_agent import AssistantAgent
from agents.qc_agent import QCAgent

from core.webhook_server import build_webhook_app, start_webhook_server
from core.agent_relay import AgentRelay
from tools.agent_relay_tools import AgentRelayTool


# from agents.coder_agent import CoderAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("Launcher")

# 1. 先尝试找本地的 .env (适合你在 MacBook 上开发)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
local_env_path = os.path.join(ROOT_DIR, '.env')

if os.path.exists(local_env_path):
    load_dotenv(local_env_path)
    logger.info(f"📂 已加载本地配置文件: {local_env_path}")
else:
    # 2. 如果找不到文件，就默认我们是在 Docker 里
    # 这时候变量已经由 Portainer 注入进来了，直接用就行
    logger.info("🚀 未找到本地 .env 文件，将使用系统/Docker环境变量启动。")


async def main():
    logger.info("🔥 正在唤醒 Agent Team...")

    services = []

    # 1. 尝试组装 Scheduler
    sched_pack = ScheduleAgent.build_from_env()
    if sched_pack:
        services.append(sched_pack)

    # 3. 尝试组装 DesignAgent (新增)
    design_pack = DesignAgent.build_from_env()
    if design_pack:
        services.append(design_pack)

    # 4. 尝试组装 ConceptAgent (新增)
    concept_pack = ConceptAgent.build_from_env()
    if concept_pack:
        services.append(concept_pack)

    # 5. 尝试组装 StoryboardAgent (新增)
    storyboard_pack = StoryboardAgent.build_from_env()
    if storyboard_pack:
        services.append(storyboard_pack)

    # 6. 尝试组装 AssistantAgent (新增)
    assistant_pack = AssistantAgent.build_from_env()
    if assistant_pack:
        services.append(assistant_pack)

    # 7. 尝试组装 ProduceAgent (新增)
    produce_pack = ProduceAgent.build_from_env()
    if produce_pack:
        services.append(produce_pack)

    # 8. 尝试组装 QC Agent (新增)
    qc_pack = QCAgent.build_from_env()
    if qc_pack:
        services.append(qc_pack)

    if not services:
        logger.error("❌ 无可用 Agent。")
        return

    # 2. 轻量级 Agent 通信中继（可镜像到飞书）
    relay = AgentRelay({svc["name"]: svc["agent"] for svc in services})
    for svc in services:
        agent = svc["agent"]
        setattr(agent, "relay", relay)
        relay_tool = AgentRelayTool(relay, sender_name=agent.name)
        agent.toolkit.register_tool_function(relay_tool.send_agent_message)
        # 为监制 agent 添加广播能力，也可以给所有 agent 添加
        if agent.name == "ProduceAgent":
            agent.toolkit.register_tool_function(relay_tool.broadcast_message)

    # 3. Webhook 服务启动
    webhook_enabled = os.environ.get("WEBHOOK_ENABLED", "1") == "1"
    if webhook_enabled:
        os.environ.setdefault("LARK_EVENT_MODE", "webhook")
        webhook_host = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
        webhook_port = int(os.environ.get("WEBHOOK_PORT", "8000"))
        main_loop = asyncio.get_running_loop()
        
        # 全局 Verification Token（所有应用共用）
        global_verification_token = os.environ.get("FEISHU_VERIFICATION_TOKEN")

        prefix_map = {
            "Scheduler": "SCHEDULER",
            "DesignAgent": "DESIGN",
            "ConceptAgent": "CONCEPT",
            "StoryboardAgent": "STORYBOARD",
            "AssistantAgent": "ASSISTANT",
            "ProduceAgent": "PRODUCE",
            "QCAgent": "QC",
        }

        endpoint_map = {}
        for svc in services:
            name = svc["name"]
            manager = svc["manager"]
            prefix = prefix_map.get(name, name.upper())

            # 默认使用简短小写路径（design/concept/storyboard/produce/scheduler），可通过环境变量覆盖
            default_endpoint = prefix.lower()
            endpoint = os.environ.get(f"{prefix}_WEBHOOK_PATH") or default_endpoint
            
            # 优先使用应用级别的 token，其次使用全局 token
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
        logger.info(f"🌐 Webhook 服务已启动: http://{webhook_host}:{webhook_port}/{{endpoint}}")

    # 4. 批量点火 - 使用 asyncio.gather 实现真正的并发执行
    tasks = []
    for svc in services:
        agent = svc["agent"]
        manager = svc["manager"]

        # 🔥 关键点：Launcher 不再管怎么跑，直接调用 Agent 自己的启动方法
        # 这就是你想要的：生命周期模板由 Agent 自己决定
        # 使用 asyncio.gather 让所有 Agent 并发运行
        tasks.append(agent.start_service(manager))

    if tasks:
        await asyncio.gather(*tasks)

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