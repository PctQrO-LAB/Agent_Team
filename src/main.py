import os
import sys
import json
import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

# --- AgentScope ---
import agentscope
from agentscope.message import Msg

# --- 项目模块 ---
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.schedule_agent import ScheduleAgent
from config.prompts import SCHEDULE_SYSTEM_PROMPT
from core.lark_manager import LarkManager
from core.load_model import load_model_config

# --- 配置日志 ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Main")

# ==========================================
# 1. 强制加载环境变量
# ==========================================
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT_DIR, '.env')
load_dotenv(ENV_PATH)

APP_ID = os.environ.get("SCHEDULER_APP_ID")
APP_SECRET = os.environ.get("SCHEDULER_APP_SECRET")
USER_OPEN_ID = os.environ.get("USER_OPEN_ID")

if not APP_ID or not APP_SECRET:
    logger.critical(f"❌ 环境变量加载失败！请检查文件: {ENV_PATH}")
    sys.exit(1)

# --- 结束语关键词 ---
EXIT_KEYWORDS = ["辛苦", "结束", "再见", "晚安", "bye", "退下", "总结本次"]


async def main():
    """程序主入口"""

    # 2. 加载模型配置
    try:
        llm_config = load_model_config("deepseek_config")
        # 确保配置格式正确传给 agentscope
        model_configs = [llm_config]
        logger.info("✅ AgentScope 初始化成功")
    except Exception as e:
        logger.error(f"❌ 模型加载失败: {e}")
        return

    # 3. 初始化 ScheduleAgent
    try:
        agent = ScheduleAgent(name="Scheduler")
        logger.info("✅ Agent 初始化成功")
    except Exception as e:
        logger.error(f"❌ Agent 初始化失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return

    # 4. 初始化 LarkManager
    lark_manager = LarkManager(APP_ID, APP_SECRET)

    # ==========================================
    # 消息处理逻辑 (数据清洗版)
    # ==========================================
    async def process_user_message(text: str, sender_id: str, chat_id: str):
        logger.info(f"📩 收到消息: {text}")

        msg = Msg(name="user", content=text, role="user")

        try:
            logger.info("🧠 Agent 开始思考...")

            response = await asyncio.wait_for(
                agent(msg),
                timeout=60.0
            )

            # --- 🧹 数据清洗逻辑 (核心修改) ---
            raw_content = response.content if response else None

            if raw_content is None:
                reply_content = "🤖 (无内容)"
            elif isinstance(raw_content, str):
                # 如果本来就是字符串，直接用
                reply_content = raw_content
            elif isinstance(raw_content, list):
                # 如果是列表 (AgentScope 富文本格式)，提取所有 text 字段
                # 示例: [{'type': 'text', 'text': '你好'}]
                texts = [item.get('text', '') for item in raw_content if
                         isinstance(item, dict) and item.get('type') == 'text']
                reply_content = "\n".join(texts)

                # 如果列表里全是空或者解析失败，转为字符串兜底
                if not reply_content.strip():
                    reply_content = str(raw_content)
            else:
                # 其他类型直接转字符串
                reply_content = str(raw_content)

            logger.info(f"✅ 准备回复 (清洗后): {reply_content[:20]}...")

            # 发回飞书
            await lark_manager.send_message(chat_id, reply_content, receive_id_type="chat_id")

        except asyncio.TimeoutError:
            await lark_manager.send_message(chat_id, "❌ Agent 思考超时，请检查网络。", receive_id_type="chat_id")
        except Exception as e:
            logger.error(f"处理异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await lark_manager.send_message(chat_id, f"❌ 系统错误: {str(e)}", receive_id_type="chat_id")

        # 退出检测
        if any(k in text for k in EXIT_KEYWORDS):
            logger.info("🛑 触发退出机制，清理记忆...")
            if hasattr(agent, "memory") and agent.memory:
                agent.memory.clear()
            await lark_manager.send_message(chat_id, "✅ 会话结束，短期记忆已清理。", receive_id_type="chat_id")

    # 注册回调
    lark_manager.set_message_handler(process_user_message)

    # 5. 初始化定时任务
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

    async def trigger_report(report_type: str, prompt: str):
        if not USER_OPEN_ID: return
        logger.info(f"⏰ 触发报告: {report_type}")

        msg = Msg(name="system_trigger", content=prompt, role="user")

        try:
            response = await agent(msg)

            # --- 🧹 同样的数据清洗 ---
            raw_content = response.content
            if isinstance(raw_content, list):
                texts = [item.get('text', '') for item in raw_content if
                         isinstance(item, dict) and item.get('type') == 'text']
                final_text = "\n".join(texts)
            else:
                final_text = str(raw_content)

            await lark_manager.send_message(USER_OPEN_ID, final_text, receive_id_type="open_id")

            if report_type == "晚报" and hasattr(agent, "memory"):
                agent.memory.clear()
        except Exception as e:
            logger.error(f"定时报告执行失败: {e}")

    # 配置三报
    scheduler.add_job(trigger_report, 'cron', hour=8, minute=0,
                      args=["晨报", "[系统指令] 现在是晨报时间。请读取笔记本，审计今日日程，并给出建议。"])
    scheduler.add_job(trigger_report, 'cron', hour=12, minute=0,
                      args=["午报", "[系统指令] 现在是午报时间。请检查上午任务完成情况，确认下午安排。"])
    scheduler.add_job(trigger_report, 'cron', hour=20, minute=0, args=["晚报",
                                                                       "[系统指令] 现在是晚报时间。请总结全天工作，提取行为规律(add_pattern)，并清理已完成事项。"])

    scheduler.start()
    logger.info("⏰ 定时任务已启动")

    # 6. 启动飞书监听
    logger.info("🚀 服务已就绪，开始监听...")

    # 启动非阻塞监听 (多线程)
    lark_manager.start()

    # 7. 主线程保活
    logger.info("🌈 系统运行中 (按 Ctrl+C 退出)...")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 程序已退出")