import json
import logging
import asyncio
import threading
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from lark_oapi.ws import Client as WebSocketClient

# 获取日志记录器
logger = logging.getLogger("LarkManager")


class LarkManager:
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.message_handler = None

        # 1. 记录主线程的事件循环
        try:
            self.main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self.main_loop = asyncio.new_event_loop()

        # 2. 初始化 API 客户端
        self.api_client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()

        # 3. 初始化事件分发器
        self.event_dispatcher = lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(self._handle_message_event) \
            .build()

        # 4. 初始化 WebSocket 客户端
        self.ws_client = WebSocketClient(
            app_id,
            app_secret,
            event_handler=self.event_dispatcher,
            log_level=lark.LogLevel.INFO
        )

    def set_message_handler(self, handler):
        """设置异步回调函数"""
        self.message_handler = handler

    def _handle_message_event(self, data: P2ImMessageReceiveV1) -> None:
        """
        [子线程] 收到飞书消息的回调
        """
        # 简单解析，看是否需要处理
        event = data.event
        message = event.message

        # ---------------------------------------------------------
        # 🛡️ 核心过滤逻辑：群聊防打扰 & @检测
        # ---------------------------------------------------------
        chat_type = message.chat_type  # 'p2p' (私聊) 或 'group' (群聊)
        mentions = getattr(message, "mentions", [])  # 获取被@的人列表

        # 如果是群聊，且没有人被@，直接忽略，不打印日志，不处理
        if chat_type == "group" and not mentions:
            return

            # 解析文本内容
        try:
            content = json.loads(message.content)
            user_text = content.get("text", "").strip()
        except:
            return

            # 🧹 数据清洗：如果是群聊且有@，尝试把 @机器人的名字 从文本中删掉
        # 这样 Agent 看到的只是 "帮我定日程"，而不是 "@CoveyManager 帮我定日程"
        if chat_type == "group" and mentions:
            for mention in mentions:
                # mention.key 就是 "@用户" 的字符串
                if mention.key:
                    user_text = user_text.replace(mention.key, "").strip()

        # ---------------------------------------------------------

        sender_id = event.sender.sender_id.open_id
        chat_id = message.chat_id

        # ⚡️ 跨线程调用
        if self.message_handler:
            asyncio.run_coroutine_threadsafe(
                self.message_handler(user_text, sender_id, chat_id),
                self.main_loop
            )

    async def send_message(self, receive_id: str, text: str, receive_id_type="open_id"):
        """[主线程] 发送 Markdown 卡片消息"""
        if not text: return

        # 构造 Markdown 卡片
        card_content = {
            "config": {"wide_screen_mode": True},
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": text
                    }
                }
            ]
        }

        request_body = CreateMessageRequestBody.builder() \
            .receive_id(receive_id) \
            .msg_type("interactive") \
            .content(json.dumps(card_content)) \
            .build()

        request = CreateMessageRequest.builder() \
            .receive_id_type(receive_id_type) \
            .request_body(request_body) \
            .build()

        loop = asyncio.get_running_loop()
        try:
            resp = await loop.run_in_executor(None, lambda: self.api_client.im.v1.message.create(request))
            if not resp.success():
                logger.error(f"❌ 发送失败: {resp.code} - {resp.msg}")
            else:
                logger.info(f"✅ 回复已送达")
        except Exception as e:
            logger.error(f"❌ 发送异常: {e}")

    def start(self):
        """[非阻塞启动]"""
        print(f"📡 正在启动飞书长连接 (独立线程模式)...")
        t = threading.Thread(target=self.ws_client.start, daemon=True)
        t.start()