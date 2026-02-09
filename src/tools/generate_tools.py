import requests
import json
import os
from typing import List, Optional
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock


class GenerationTool:
    """
    [生产委托工具] (简化版)
    职责：仅发送 Prompt 和 路径，无需关心发给谁。
    对接 n8n Webhook，用于替代 Anycross 飞书集成。
    """

    def __init__(self):
        # n8n Webhook 地址，兼容旧的 ANYCROSS_IMAGE_URL
        self.webhook_url = os.environ.get("N8N_IMAGE_WEBHOOK_URL") or os.environ.get("ANYCROSS_IMAGE_URL")

    def generate_image(
        self,
        prompt: str,
        target_path: str,
        author_agent: Optional[str] = None,
        reference_images: Optional[List[str]] = None,
        mode: str = "text2img",
    ) -> ToolResponse:
        """
        [委托生成] 发送生图指令。

        Args:
            prompt: 英文提示词。
            target_path: 本地保存路径。
            author_agent: 发起委托的作者/智能体名称 (可选)。
            reference_images: 参考图 URL 列表 (可选，多图参考时传入)。
            mode: 生成模式 (text2img / img2img / multi_ref)。
        """
        if not self.webhook_url:
            return ToolResponse(content=[TextBlock(type="text", text="❌ Error: N8N_IMAGE_WEBHOOK_URL 未配置。")])

        # 📦 Payload 精简了：只传生图需要的信息
        payload = {
            "prompt": prompt,
            "target_path": target_path,
            "mode": mode,
            # chat_id 被移除了，由飞书集成平台内部决定发给谁
        }

        if author_agent:
            payload["author_agent"] = author_agent

        if reference_images:
            payload["reference_images"] = reference_images

        try:
            # 发送请求
            resp = requests.post(self.webhook_url, json=payload, timeout=10)

            if resp.status_code == 200:
                return ToolResponse(content=[TextBlock(type="text",
                                                       text=f"✅ 委托已发送 (n8n Webhook)。\nPrompt: {prompt[:50]}...\nPath: {target_path}")])
            else:
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 平台拒收: {resp.text}")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 连接异常: {e}")])