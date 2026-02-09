import json
from typing import Any, Dict, Optional, Tuple

from lark_oapi.api.im.v1 import P2ImMessageReceiveV1


def extract_message_from_p2(event: P2ImMessageReceiveV1, manager: Any, bot_name: str) -> Optional[Tuple[list, str, str]]:
    """从 v2.0 事件模型中提取文本/图片消息"""
    message = event.event.message
    sender = event.event.sender

    sender_id = sender.sender_id.open_id or sender.sender_id.user_id
    chat_id = message.chat_id
    msg_type = message.message_type

    try:
        content_json = json.loads(message.content)
    except Exception:
        return None

    msg_content = []

    if msg_type == "text":
        text = (content_json.get("text") or "").strip()

        mentions = getattr(message, "mentions", []) or []
        if mentions and bot_name:
            is_at_me = any(
                (bot_name in (m.name or "")) or ((m.name or "") in bot_name)
                for m in mentions
            )
            if not is_at_me:
                return None
            for m in mentions:
                if m.key:
                    text = text.replace(m.key, "").strip()

        if text:
            msg_content.append({"type": "text", "text": text})

        image_key = content_json.get("image_key")
        if image_key:
            url = manager._process_image_stream(message.message_id, image_key)
            if url:
                msg_content.append({"type": "image", "source": {"type": "url", "url": url}})
            else:
                msg_content.append({"type": "text", "text": "[Image Failed]"})

        if content_json.get("content"):
            msg_content = manager._parse_post_content(content_json, message.message_id)

    if msg_type == "image":
        image_key = content_json.get("image_key")
        if image_key:
            url = manager._process_image_stream(message.message_id, image_key)
            if url:
                msg_content.append({"type": "image", "source": {"type": "url", "url": url}})
            else:
                msg_content.append({"type": "text", "text": "[Image Failed]"})

    if msg_type == "post":
        msg_content = manager._parse_post_content(content_json, message.message_id)

    if not msg_content:
        return None

    return msg_content, sender_id, chat_id
