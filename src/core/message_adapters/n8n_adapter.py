import uuid
from typing import Any, Dict, List, Tuple


def extract_n8n_message(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str, str]:
    text = (payload.get("text") or "").strip()
    prompt = (payload.get("prompt") or "").strip()
    image_url = payload.get("image_url")
    image_urls = payload.get("image_urls") or []
    file_path = (payload.get("file_path") or "").strip()
    sender_id = payload.get("sender_id") or "n8n"
    lark_chat_id = payload.get("lark_chat_id") or payload.get("chat_id")
    chat_id = lark_chat_id or f"n8n:{uuid.uuid4().hex}"

    msg_content: List[Dict[str, Any]] = []
    combined_text = ""
    if text and prompt:
        combined_text = f"{text}\n\n[Prompt]\n{prompt}"
    elif text:
        combined_text = text
    elif prompt:
        combined_text = f"[Prompt]\n{prompt}"

    if combined_text:
        msg_content.append({"type": "text", "text": combined_text})

    if file_path:
        msg_content.append({"type": "text", "text": f"file_path: {file_path}"})

    urls = []
    if image_url:
        urls.append(image_url)
    if isinstance(image_urls, list):
        urls.extend([u for u in image_urls if u])

    for url in urls:
        msg_content.append({"type": "image", "source": {"type": "url", "url": url}})

    return msg_content, sender_id, chat_id
