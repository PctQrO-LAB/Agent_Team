import os
import json
import logging
import asyncio
import threading
import oss2
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from lark_oapi.ws import Client as WebSocketClient
from typing import Any, Union, List, Dict

# 引入 nest_asyncio
try:
    import nest_asyncio
except ImportError:
    nest_asyncio = None

logger = logging.getLogger("LarkManager")


class LarkManager:
    """
    [飞书网关 v8.0] 全能多模态版
    特性：
    1. 支持 Post 富文本解析（图文混排）。
    2. 自动 OSS 上传。
    3. 输出 AgentScope 标准 ImageBlock，彻底解决格式兼容问题。
    """

    def __init__(self, app_id: str, app_secret: str, bot_name: str = None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.bot_name = bot_name
        self.message_handler = None

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
                logger.info("☁️ [Init] OSS 服务已连接")
            except Exception as e:
                logger.error(f"❌ [Init] OSS 连接失败: {e}")

        # 捕获主循环
        try:
            self.main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self.main_loop = asyncio.get_event_loop()

        self.api_client = lark.Client.builder() \
            .app_id(app_id).app_secret(app_secret).log_level(lark.LogLevel.INFO).build()

    def start(self):
        """启动 WebSocket"""

        def _run_isolated_client():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            if nest_asyncio: nest_asyncio.apply(new_loop)

            def _ignore_noise(loop, context):
                if "Task.__wakeup" in context.get("message", ""): return
                loop.default_exception_handler(context)

            new_loop.set_exception_handler(_ignore_noise)

            try:
                dispatcher = lark.EventDispatcherHandler.builder("", "") \
                    .register_p2_im_message_receive_v1(self._on_ws_message).build()
                client = WebSocketClient(self.app_id, self.app_secret, event_handler=dispatcher,
                                         log_level=lark.LogLevel.INFO)
                client.start()
            except Exception as e:
                logger.error(f"❌ WebSocket 崩溃: {e}")
            finally:
                new_loop.close()

        threading.Thread(target=_run_isolated_client, daemon=True).start()

    def _on_ws_message(self, data: P2ImMessageReceiveV1) -> None:
        if not self.message_handler: return
        try:
            event = data.event
            message = event.message
            content_json = json.loads(message.content)
            msg_type = message.message_type

            # 默认为空列表
            msg_content = []

            # --- 文本消息 ---
            if msg_type == "text":
                text = content_json.get("text", "").strip()
                if text:
                    msg_content.append({"type": "text", "text": text})

            # --- 图片消息 ---
            elif msg_type == "image":
                image_key = content_json.get("image_key")
                # 上传并生成标准 Block
                img_block = self._create_image_block(message.message_id, image_key)
                if img_block:
                    msg_content.append({"type": "text", "text": "User sent an image:"})  # 辅助文本
                    msg_content.append(img_block)
                else:
                    msg_content.append({"type": "text", "text": f"[System: Image upload failed. Key: {image_key}]"})

            # --- 🔥 Post 富文本 (图文混排修复) ---
            elif msg_type == "post":
                # 🔥 修改点：传入 message.message_id
                # 这样 _parse_post_content 才有权限去下载 Post 里的图片
                msg_content = self._parse_post_content(content_json, message.message_id)

            else:
                msg_content = [{"type": "text", "text": f"[System: Receive unsupported message type: {msg_type}]"}]

            # --- 群聊过滤 ---
            sender_id = event.sender.sender_id.open_id
            if message.chat_type == "group":
                mentions = getattr(message, "mentions", [])
                if not mentions: return
                if self.bot_name:
                    is_at_me = any(m.name == self.bot_name for m in mentions)
                    if not is_at_me: return
                    # 清理 @文本 (针对 Text Block)
                    for block in msg_content:
                        if block.get("type") == "text":
                            for m in mentions:
                                if m.key: block["text"] = block["text"].replace(m.key, "").strip()

            # --- 投递 ---
            if self.main_loop and not self.main_loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    self.message_handler(msg_content, sender_id, message.chat_id),
                    self.main_loop
                )

        except Exception as e:
            logger.error(f"消息处理异常: {e}")

    def _process_image_stream(self, message_id, image_key):
        """下载流 -> 上传 OSS -> 返回 URL"""
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
            logger.error(f"OSS Error: {e}")
            return None

    def _create_image_block(self, message_id, image_key):
        """辅助函数：生成 AgentScope 标准 ImageBlock"""
        url = self._process_image_stream(message_id, image_key)
        if url:
            # 🔥 关键修正：使用 AgentScope 标准格式 (type='image', source={type='url'...})
            # 这样 DashScopeChatFormatter 才能正确识别并转换
            return {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": url
                }
            }
        return None

    def _parse_post_content(self, content_json, message_id):
        """
        解析 Post 富文本，支持提取文字和图片（自动上传 OSS）
        返回: List[Dict] (符合 AgentScope 标准的多模态消息列表)
        """
        msg_content = []
        try:
            # Post 结构通常是: content -> list of lines -> list of elements
            # 这是一个二维数组结构
            for lines in content_json.get("content", []):
                for elem in lines:

                    # A. 处理文字
                    if elem["tag"] == "text":
                        text = elem.get("text", "").strip()
                        if text:
                            msg_content.append({"type": "text", "text": text})

                    # B. 🔥 处理图片 (新增逻辑)
                    elif elem["tag"] == "img":
                        image_key = elem.get("image_key")

                        # 1. 复用上传逻辑 (直接上云拿到 URL)
                        oss_url = self._process_image_stream(message_id, image_key)

                        # 2. 构造标准 ImageBlock
                        if oss_url:
                            msg_content.append({
                                "type": "image",
                                "source": {
                                    "type": "url",
                                    "url": oss_url
                                }
                            })
                        else:
                            # 如果上传失败，留个占位符
                            msg_content.append({"type": "text", "text": "[Image Upload Failed]"})

        except Exception as e:
            logger.error(f"Post 解析失败: {e}")
            return [{"type": "text", "text": "[Complex Post Error]"}]

        # 如果解析结果为空（比如只发了空行），给个默认值
        if not msg_content:
            return [{"type": "text", "text": "[Empty Post]"}]

        return msg_content

    async def reply(self, chat_id, response):
        # 简单处理回复：提取文本内容发送
        clean_text = ""
        if isinstance(response, str):
            clean_text = response
        elif isinstance(response, list):
            # 如果是列表，提取所有 text 块
            texts = [b.get("text", "") for b in response if isinstance(b, dict) and b.get("type") == "text"]
            clean_text = "\n".join(texts)
        elif hasattr(response, 'text'):
            clean_text = response.text
        else:
            clean_text = str(response)

        card = {"config": {"wide_screen_mode": True},
                "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": clean_text}}]}
        req = CreateMessageRequest.builder().receive_id_type("chat_id") \
            .request_body(CreateMessageRequestBody.builder().receive_id(chat_id).msg_type("interactive")
                          .content(json.dumps(card)).build()).build()
        await asyncio.to_thread(lambda: self.api_client.im.v1.message.create(req))

    def bind_handler(self, func):
        self.message_handler = func