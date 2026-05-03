import uuid
import json
from typing import Any, Dict, List, Tuple


def extract_n8n_message(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str, str]:
    # 提取常见基础字段
    text = (payload.get("text") or "").strip()
    prompt = (payload.get("prompt") or "").strip()
    image_url = payload.get("image_url")
    image_urls = payload.get("image_urls") or []
    if isinstance(image_urls, str):
        image_urls = [image_urls]
        
    sender_id = payload.get("sender_id") or "n8n"
    lark_chat_id = payload.get("lark_chat_id") or payload.get("chat_id")
    chat_id = lark_chat_id or f"n8n:{uuid.uuid4().hex}"

    msg_content: List[Dict[str, Any]] = []
    
    # 将除了特定保留字之外的所有额外参数打包作为附属信息传给 AI
    ignored_keys = {"image_url", "image_urls", "sender_id", "lark_chat_id", "chat_id", "text", "source"}
    extra_params = {k: v for k, v in payload.items() if k not in ignored_keys and v}

    text_parts = []
    if text:
        text_parts.append(text)
    if prompt:
        text_parts.append(f"[Prompt]\n{prompt}")
        
    if extra_params:
        extra_info = []
        for k, v in extra_params.items():
            if isinstance(v, (dict, list)):
                extra_info.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
            else:
                extra_info.append(f"{k}: {v}")
        text_parts.append("[Extra Params from n8n]\n" + "\n".join(extra_info))

    if text_parts:
        msg_content.append({"type": "text", "text": "\n\n".join(text_parts)})

    # 处理单图和多图
    urls = []
    if image_url:
        urls.append(image_url)
    if image_urls and isinstance(image_urls, list):
        urls.extend([u for u in image_urls if u])

    for url in urls:
        if url:
            msg_content.append({"type": "image", "source": {"type": "url", "url": url}})

    return msg_content, sender_id, chat_id
