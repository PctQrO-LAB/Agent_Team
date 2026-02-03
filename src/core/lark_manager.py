import os
import json
import logging
import asyncio
import oss2
import lark_oapi as lark
from lark_oapi.api.contact.v3 import BatchGetIdUserRequest, BatchGetIdUserRequestBody
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody, GetMessageResourceRequest
from typing import Any, Union, List, Dict

# 设置日志格式，移除统一的 Launcher logger，改为动态获取
logging.basicConfig(level=logging.INFO)


class LarkManager:
    """
    飞书出站客户端：仅负责主动调用飞书 API（发消息、取资源、OSS 上传等）。
    不再持有 WebSocket/事件派发；入站由 webhook 负责。
    """

    def __init__(self, app_id: str, app_secret: str, bot_name: str = "UnknownBot"):
        self.app_id = app_id
        self.app_secret = app_secret
        self.bot_name = bot_name
        self.message_handler = None  # 保留给 webhook 注入回调所用

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

        # --- HTTP Client ---
        self.api_client = lark.Client.builder() \
            .app_id(app_id).app_secret(app_secret).log_level(lark.LogLevel.INFO).build()
        self._cached_open_id = None

    def _resolve_user_open_id(self) -> str | None:
        if self._cached_open_id:
            return self._cached_open_id

        user_email = os.environ.get("USER_EMAIL")
        user_mobile = os.environ.get("USER_MOBILE")
        if not user_email and not user_mobile:
            return os.environ.get("USER_OPEN_ID")

        try:
            body_builder = BatchGetIdUserRequestBody.builder()
            if user_email:
                body_builder.emails([user_email])
            if user_mobile:
                body_builder.mobiles([user_mobile])
            body = body_builder.build()

            req = BatchGetIdUserRequest.builder() \
                .user_id_type("open_id") \
                .request_body(body) \
                .build()

            resp = self.api_client.contact.v3.user.batch_get_id(req)
            if resp.success() and resp.data and resp.data.user_list:
                open_id = resp.data.user_list[0].user_id
                self._cached_open_id = open_id
                return open_id
        except Exception as e:
            self.logger.error(f"❌ OpenID resolve failed: {e}")

        return os.environ.get("USER_OPEN_ID")

    def start(self):
        """Webhook 模式下无需启动任何长连接，保留接口作兼容。"""
        self.logger.info("ℹ️ Webhook 模式：LarkManager 不再启动 WebSocket，只负责出站调用")

    def _process_image_stream(self, message_id, image_key):
        if not self.bucket:
            return None
        try:
            req = GetMessageResourceRequest.builder() \
                .message_id(message_id).file_key(image_key).type("image").build()
            resp = self.api_client.im.v1.message_resource.get(req)
            if not resp.success():
                return None

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

    async def reply(self, receive_id, response, receive_id_type: str = "chat_id"):
        clean_text = ""
        if isinstance(response, str):
            clean_text = response
        elif isinstance(response, list):
            clean_text = "\n".join([b.get("text", "") for b in response if b.get("type") == "text"])
        elif hasattr(response, 'text'):
            clean_text = response.text
        else:
            clean_text = str(response)

        if isinstance(receive_id, str) and receive_id.startswith("n8n:"):
            fallback_open_id = self._resolve_user_open_id()
            if fallback_open_id:
                receive_id = fallback_open_id
                receive_id_type = "open_id"
            else:
                self.logger.error("❌ No USER_OPEN_ID/USER_EMAIL/USER_MOBILE configured.")
                return

        card = {"config": {"wide_screen_mode": True},
                "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": clean_text}}]}
        req = CreateMessageRequest.builder().receive_id_type(receive_id_type) \
            .request_body(CreateMessageRequestBody.builder().receive_id(receive_id).msg_type("interactive")
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