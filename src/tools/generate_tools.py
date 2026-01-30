import requests
import json
import os
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock


class GenerationTool:
    """
    [生产委托工具] (简化版)
    职责：仅发送 Prompt 和 路径，无需关心发给谁。
    """

    def __init__(self):
        # 你的 Webhook 地址
        self.webhook_url = os.environ.get("ANYCROSS_IMAGE_URL")

    def generate_image(self, prompt: str, target_path: str) -> ToolResponse:
        """
        [委托生成] 发送生图指令。

        Args:
            prompt: 英文提示词。
            target_path: 本地保存路径。
        """
        if not self.webhook_url:
            return ToolResponse(content=[TextBlock(type="text", text="❌ Error: ANYCROSS_IMAGE_URL 未配置。")])

        # 📦 Payload 精简了：只传生图需要的信息
        payload = {
            "prompt": prompt,
            "target_path": target_path
            # chat_id 被移除了，由飞书集成平台内部决定发给谁
        }

        try:
            # 发送请求
            resp = requests.post(self.webhook_url, json=payload, timeout=10)

            if resp.status_code == 200:
                return ToolResponse(content=[TextBlock(type="text",
                                                       text=f"✅ 委托已发送 (Cloud Mode)。\nPrompt: {prompt[:50]}...\nPath: {target_path}")])
            else:
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 平台拒收: {resp.text}")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 连接异常: {e}")])