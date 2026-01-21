import os
import json
import logging
import asyncio
import oss2
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from typing import Any, Union, List, Dict

# 引入 nest_asyncio
try:
    import nest_asyncio
except ImportError:
    nest_asyncio = None

# 设置日志格式，移除统一的 Launcher logger，改为动态获取
logging.basicConfig(level=logging.INFO)


class LarkManager:
    """
    [飞书网关 v10.0 - 多实例增强版]
    1. 增加线程异常捕获，防止 WebSocket 静默崩溃。
    2. 日志增加 bot_name 前缀，便于多 Agent 调试。
    """

    def __init__(self, app_id: str, app_secret: str, bot_name: str = "UnknownBot"):
        self.app_id = app_id
        self.app_secret = app_secret
        self.bot_name = bot_name
        self.message_handler = None

        # 独立的 Logger
        self.logger = logging.getLogger(f"Lark_{bot_name}")

        # --- OSS 初始化 ---
        self.oss_bucket_name = os.environ.get("OSS_BUCKET_NAME")
        self.oss_endpoint = os.environ.get("OSS_ENDPOINT")
        self.oss_key_id = os.environ.get("OSS_ACCESS_KEY_ID")
        self.oss_key_secret = os.environ.get("OSS_ACCESS_KEY_SECRET")

        self.bucket = None
        if self.oss_key_id and self.oss_key_secret:
            try:
                auth = oss2.Auth(self.oss_key_id, self.oss_key_secret)
                self.bucket = oss2.Bucket(auth, self.oss_endpoint, self.oss_bucket_name)
                self.logger.info("☁️ [Init] OSS 服务已连接")
            except Exception as e:
                self.logger.error(f"❌ [Init] OSS 连接失败: {e}")

        # --- 异步 Loop 获取 ---
        try:
            self.main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self.main_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.main_loop)

        if nest_asyncio:
            nest_asyncio.apply(self.main_loop)

        # --- 1. HTTP Client ---
        self.api_client = lark.Client.builder() \
            .app_id(app_id).app_secret(app_secret).log_level(lark.LogLevel.INFO).build()

        # --- 2. WebSocket Client ---
        event_handler = lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(self._on_ws_message) \
            .build()

        self.ws = lark.ws.Client(
            app_id,
            app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO
        )

    def start(self):
        """
        [启动服务] 增加 Future 回调以捕获线程中的崩溃
        """
        if not self.ws:
            self.logger.error("❌ WebSocket Client 未初始化")
            return

        def _handle_ws_crash(future):
            try:
                future.result()  # 如果线程里抛出异常，这里会重新抛出
            except Exception as e:
                self.logger.error(f"❌ 严重错误: WebSocket 进程意外崩溃! 错误: {e}", exc_info=True)

        try:
            loop = asyncio.get_running_loop()
            # 🔥 捕获 Future 对象
            future = loop.run_in_executor(None, self.ws.start)
            # 添加回调，如果线程挂了，通知主线程
            future.add_done_callback(_handle_ws_crash)

            self.logger.info(f"✅ WebSocket 服务已在后台启动")
        except RuntimeError:
            self.logger.warning(f"⚠️ 无运行中 Loop，降级为阻塞启动")
            self.ws.start()

    def _on_ws_message(self, data: P2ImMessageReceiveV1) -> None:
        """回调函数"""
        # 🔥 调试日志：确认是否收到了底层事件
        # self.logger.info("⚡ 收到底层 WebSocket 事件...")

        if not self.message_handler: return
        try:
            event = data.event
            message = event.message
            content_json = json.loads(message.content)
            msg_type = message.message_type

            msg_content = []

            # A. 纯文本
            if msg_type == "text":
                text = content_json.get("text", "").strip()
                if text:
                    msg_content.append({"type": "text", "text": text})

            # B. 图片
            elif msg_type == "image":
                image_key = content_json.get("image_key")
                img_block = self._create_image_block(message.message_id, image_key)
                if img_block:
                    msg_content.append({"type": "text", "text": "User sent an image:"})
                    msg_content.append(img_block)
                else:
                    msg_content.append({"type": "text", "text": f"[System: Image upload failed]"})

            # C. Post 富文本
            elif msg_type == "post":
                msg_content = self._parse_post_content(content_json, message.message_id)

            else:
                msg_content = [{"type": "text", "text": f"[Unsupported: {msg_type}]"}]

            # D. 群聊过滤
            sender_id = event.sender.sender_id.open_id
            if message.chat_type == "group":
                mentions = getattr(message, "mentions", [])
                if not mentions: return
                # 这里的 self.bot_name 是我们在 __init__ 里传入的名字
                # 确保它和飞书群里 @ 的名字（或别名）一致，否则这里会过滤掉
                if self.bot_name:
                    # 模糊匹配：只要 mention 的 name 包含 bot_name 或者是 bot_name 的一部分
                    is_at_me = any(self.bot_name in m.name or m.name in self.bot_name for m in mentions)
                    if not is_at_me:
                        # self.logger.debug(f"群聊消息忽略，未 @ 我 ({self.bot_name})")
                        return

                    # 清理 @文本
                    for block in msg_content:
                        if block.get("type") == "text":
                            for m in mentions:
                                if m.key: block["text"] = block["text"].replace(m.key, "").strip()

            # E. 投递
            self.logger.info(f"📩 收到有效消息 (User: {sender_id}), 正在投递给 Agent...")
            if self.main_loop and not self.main_loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    self.message_handler(msg_content, sender_id, message.chat_id),
                    self.main_loop
                )

        except Exception as e:
            self.logger.error(f"消息处理异常: {e}", exc_info=True)

    def _process_image_stream(self, message_id, image_key):
        if not self.bucket: return None
        try:
            req = GetMessageResourceRequest.builder() \
                .message_id(message_id).file_key(image_key).type("image").build()
            resp = self.api_client.im.v1.message_resource.get(req)
            if not resp.success(): return None

            object_name = f"agent_images/{message_id}_{image_key}.jpg"
            self.bucket.put_object(object_name, resp.file)
            return self.bucket.sign_url('GET', object_name, 3600)
        except Exception as e:
            self.logger.error(f"OSS Error: {e}")
            return None

    def _create_image_block(self, message_id, image_key):
        url = self._process_image_stream(message_id, image_key)
        if url:
            return {"type": "image", "source": {"type": "url", "url": url}}
        return None

    def _parse_post_content(self, content_json, message_id):
        msg_content = []
        try:
            for lines in content_json.get("content", []):
                for elem in lines:
                    if elem["tag"] == "text":
                        text = elem.get("text", "").strip()
                        if text: msg_content.append({"type": "text", "text": text})
                    elif elem["tag"] == "img":
                        image_key = elem.get("image_key")
                        oss_url = self._process_image_stream(message_id, image_key)
                        if oss_url:
                            msg_content.append({"type": "image", "source": {"type": "url", "url": oss_url}})
                        else:
                            msg_content.append({"type": "text", "text": "[Image Failed]"})
        except Exception:
            return [{"type": "text", "text": "[Post Error]"}]
        return msg_content if msg_content else [{"type": "text", "text": "[Empty Post]"}]

    async def reply(self, chat_id, response):
        clean_text = ""
        if isinstance(response, str):
            clean_text = response
        elif isinstance(response, list):
            clean_text = "\n".join([b.get("text", "") for b in response if b.get("type") == "text"])
        elif hasattr(response, 'text'):
            clean_text = response.text
        else:
            clean_text = str(response)

        card = {"config": {"wide_screen_mode": True},
                "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": clean_text}}]}
        req = CreateMessageRequest.builder().receive_id_type("chat_id") \
            .request_body(CreateMessageRequestBody.builder().receive_id(chat_id).msg_type("interactive")
                          .content(json.dumps(card)).build()).build()

        # 增加回复的错误捕获
        try:
            resp = await asyncio.to_thread(lambda: self.api_client.im.v1.message.create(req))
            if not resp.success():
                self.logger.error(f"❌ 回复失败: code={resp.code}, msg={resp.msg}")
        except Exception as e:
            self.logger.error(f"❌ 回复异常: {e}")

    def bind_handler(self, func):
        self.message_handler = func