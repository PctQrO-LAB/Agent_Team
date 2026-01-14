import json
import logging
import asyncio
import threading
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from lark_oapi.ws import Client as WebSocketClient
from typing import Any

# 🔥 引入补丁
try:
    import nest_asyncio
except ImportError:
    nest_asyncio = None

logger = logging.getLogger("LarkManager")


class LarkManager:
    """
    [飞书翻译器]
    修复版 v4.0: 引入 nest_asyncio 彻底解决 Loop 冲突
    """

    def __init__(self, app_id: str, app_secret: str, bot_name: str = None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.bot_name = bot_name
        self.message_handler = None

        # 1. 捕获主线程 Loop
        try:
            self.main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self.main_loop = asyncio.get_event_loop()

        self.ws_client = None
        self.event_dispatcher = None

        self.api_client = lark.Client.builder() \
            .app_id(app_id).app_secret(app_secret).log_level(lark.LogLevel.INFO).build()

    # ==========================
    # 1. 启动监听
    # ==========================
    def start(self):
        """启动 WebSocket 长连接"""

        def _run_isolated_client():
            # [Step A] 创建新 Loop
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)

            # 🔥 [关键补丁] 允许 Loop 嵌套/重入
            if nest_asyncio:
                nest_asyncio.apply(new_loop)
            else:
                logger.warning("⚠️ 未检测到 nest_asyncio，可能会导致 Loop 冲突！建议 pip install nest_asyncio")

            thread_id = threading.get_ident()
            logger.info(f"🧵 [Thread-{thread_id}] 正在启动 WebSocket (AppID: {self.app_id[-6:]})...")

            try:
                # [Step B] 子线程创建组件
                self.event_dispatcher = lark.EventDispatcherHandler.builder("", "") \
                    .register_p2_im_message_receive_v1(self._on_ws_message) \
                    .build()

                self.ws_client = WebSocketClient(
                    self.app_id,
                    self.app_secret,
                    event_handler=self.event_dispatcher,
                    log_level=lark.LogLevel.INFO
                )

                # [Step C] 启动 (阻塞)
                self.ws_client.start()

            except Exception as e:
                logger.error(f"❌ WebSocket 在线程 {thread_id} 启动崩溃: {e}")
            finally:
                new_loop.close()



        # 启动守护线程
        t = threading.Thread(target=_run_isolated_client, daemon=True)
        t.start()

    # ==========================
    # 2. 消息清洗
    # ==========================
    def _on_ws_message(self, data: P2ImMessageReceiveV1) -> None:
        if not self.message_handler: return

        try:
            event = data.event
            message = event.message
            content_json = json.loads(message.content)

            msg_type = message.message_type

            raw_text = ""
            if msg_type == "text":
                raw_text = content_json.get("text", "").strip()
            elif msg_type == "image":
                image_key = content_json.get("image_key")
                raw_text = f"[System: User sent an image. MessageID: {message.message_id}, ImageKey: {image_key}]"
            elif msg_type == "post":
                raw_text = self._parse_post_content(content_json)
            else:
                raw_text = f"[System: Receive unsupported message type: {msg_type}]"

            sender_id = event.sender.sender_id.open_id
            chat_id = message.chat_id

            # 群聊 @ 判断
            if message.chat_type == "group":
                mentions = getattr(message, "mentions", [])
                if not mentions: return

                if self.bot_name:
                    is_at_me = False
                    for mention in mentions:
                        # 调试日志
                        if "Prompt" in str(self.bot_name):
                            print(f"🧐 [NameCheck] 收到@: '{mention.name}' | 我的名字: '{self.bot_name}'")

                        if mention.name == self.bot_name:
                            is_at_me = True
                            if mention.key:
                                raw_text = raw_text.replace(mention.key, "").strip()
                    if not is_at_me: return
                else:
                    for mention in mentions:
                        if mention.key:
                            raw_text = raw_text.replace(mention.key, "").strip()

            # 投递回主线程
            if self.main_loop and not self.main_loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    self.message_handler(raw_text, sender_id, chat_id),
                    self.main_loop
                )
            else:
                logger.error("❌ 主线程 Loop 已关闭，无法处理消息")

        except Exception as e:
            logger.error(f"❌ 消息解析失败: {e}")

    def _parse_post_content(self, content_json):
        try:
            text_elems = []
            for lines in content_json.get("content", []):
                for elem in lines:
                    if elem["tag"] == "text":
                        text_elems.append(elem["text"])
            return "\n".join(text_elems)
        except:
            return "[Complex Post Message]"

    # ==========================
    # 3. 发送回复
    # ==========================
    async def reply(self, chat_id: str, agent_response: Any):
        clean_text = ""
        if agent_response is None:
            clean_text = "🤖 (无内容)"
        elif isinstance(agent_response, str):
            clean_text = agent_response
        elif isinstance(agent_response, list):
            texts = [item.get('text', '') for item in agent_response
                     if isinstance(item, dict) and item.get('type') == 'text']
            clean_text = "\n".join(texts)
            if not clean_text: clean_text = str(agent_response)
        else:
            clean_text = str(agent_response)

        if clean_text:
            await self._send_lark_card(chat_id, clean_text)

    async def _send_lark_card(self, receive_id: str, text: str):
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

        await asyncio.to_thread(lambda: self.api_client.im.v1.message.create(req))

    def bind_handler(self, async_func):
        self.message_handler = async_func