from typing import Any, List, Tuple


def normalize_message_content(content: Any) -> Tuple[Any, str]:
    """
    Normalize incoming message content for Agent consumption.

    Returns:
        model_content: content passed to Msg (can be str or list of blocks)
        plain_text: extracted text for keyword checks/logging
    """
    if content is None:
        return "", ""

    if isinstance(content, list):
        text_parts: List[str] = []
        normalized_blocks: List[Any] = []
        extra_text_blocks: List[dict] = []
        for block in content:
            if isinstance(block, dict):
                normalized_blocks.append(block)
                if block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        text_parts.append(text)
                elif block.get("type") == "image":
                    # placeholder so keyword checks still work
                    text_parts.append("[image]")
                    url = (block.get("source") or {}).get("url")
                    if url:
                        text_parts.append(f"image_url: {url}")
                        extra_text_blocks.append({"type": "text", "text": f"image_url: {url}"})
            elif isinstance(block, str):
                normalized_blocks.append(block)
                if block:
                    text_parts.append(block)
        if extra_text_blocks:
            normalized_blocks = normalized_blocks + extra_text_blocks
        return normalized_blocks, "\n".join(text_parts).strip()

    if isinstance(content, dict):
        if content.get("type") == "text":
            return [content], str(content.get("text", "")).strip()

    return content, str(content).strip()
