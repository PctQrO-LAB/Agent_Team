import json
import logging
import asyncio
import threading
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from lark_oapi.ws import Client as WebSocketClient
from typing import Any, Optional, Tuple

logger = logging.getLogger("LarkManager")


class LarkManager:
    """
    [飞书翻译器]
    职责：
    1. 负责与飞书服务器建立连接 (WebSocket)。
    2. 负责把飞书的原始 Event 清洗成纯文本 (Input Translation)。
    3. 负责把 Agent 的各种奇怪返回清洗成纯文本并发送 (Output Translation)。
    """

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.message_handler = None
        self.ws_client = None

        # 初始化 API 客户端 (用于发消息)
        self.api_client = lark.Client.builder() \
            .app_id(app_id).app_secret(app_secret).log_level(lark.LogLevel.INFO).build()

        # 初始化 WebSocket 客户端 (用于收消息)
        self.event_dispatcher = lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(self._on_ws_message) \
            .build()

        self.ws_client = WebSocketClient(
            app_id, app_secret, event_handler=self.event_dispatcher, log_level=lark.LogLevel.INFO
        )

    # ==========================
    # 1. 输入清洗 (Event -> Text)
    # ==========================
    def _on_ws_message(self, data: P2ImMessageReceiveV1) -> None:
        """WebSocket 收到消息的回调"""
        if not self.message_handler: return

        try:
            event = data.event
            message = event.message
            content_json = json.loads(message.content)

            # A. 提取基础信息
            raw_text = content_json.get("text", "").strip()
            sender_id = event.sender.sender_id.open_id
            chat_id = message.chat_id

            # B. 群聊 @ 清洗
            if message.chat_type == "group":
                mentions = getattr(message, "mentions", [])
                # 如果没 @ 机器人，或者是全员 @，都不理
                if not mentions: return

                # 把 "@机器人" 这个字符串从文本里抠掉
                for mention in mentions:
                    if mention.key:
                        raw_text = raw_text.replace(mention.key, "").strip()

            # C. 丢给业务层 (Agent)
            # 注意：这里我们使用了 asyncio.run_coroutine_threadsafe 跨线程调用
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(
                self.message_handler(raw_text, sender_id, chat_id), loop
            )

        except Exception as e:
            logger.error(f"❌ 消息解析失败: {e}")

    # ==========================
    # 2. 输出清洗 (Any -> Card/Text)
    # ==========================
    async def reply(self, chat_id: str, agent_response: Any):
        """
        [对外接口] 发送回复。会自动清洗 AgentScope 的复杂返回格式。
        """
        # A. 清洗 AgentScope 的 Response
        clean_text = ""
        if agent_response is None:
            clean_text = "🤖 (无内容)"
        elif isinstance(agent_response, str):
            clean_text = agent_response
        elif isinstance(agent_response, list):
            # 提取 list 里所有的 text 字段
            texts = [item.get('text', '') for item in agent_response
                     if isinstance(item, dict) and item.get('type') == 'text']
            clean_text = "\n".join(texts)
            if not clean_text: clean_text = str(agent_response)  # 兜底
        else:
            clean_text = str(agent_response)

        # B. 发送
        if clean_text:
            await self._send_lark_card(chat_id, clean_text)

    async def _send_lark_card(self, receive_id: str, text: str):
        """底层发送实现"""
        # 自动判断 ID 类型：如果是 ou_ 开头则是 open_id，如果是 oc_ 开头则是 chat_id
        id_type = "open_id" if receive_id.startswith("ou_") else "chat_id"

        card_content = {
            "config": {"wide_screen_mode": True},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": text}}]
        }
        req = CreateMessageRequest.builder() \
            .receive_id_type(id_type) \
            .request_body(CreateMessageRequestBody.builder()
                          .receive_id(receive_id).msg_type("interactive")
                          .content(json.dumps(card_content)).build()) \
            .build()

        # 异步调用
        resp = await asyncio.to_thread(lambda: self.api_client.im.v1.message.create(req))
        if not resp.success():
            logger.error(f"❌ 发送失败: {resp.code} - {resp.msg}")

    # ==========================
    # 3. 生命周期管理
    # ==========================
    def bind_handler(self, async_func):
        """绑定收到消息后的处理函数"""
        self.message_handler = async_func

    def start(self):
        """启动监听"""
        t = threading.Thread(target=self.ws_client.start, daemon=True)
        t.start()