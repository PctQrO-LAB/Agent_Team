from typing import Optional

from agentscope.tool import ToolResponse
from agentscope.message import TextBlock

from src.utils.message_utils import normalize_message_content

from src.core.agent_relay import AgentRelay


class AgentRelayTool:
    """
    供 LLM 调用的 Agent 间通信工具。
    """

    def __init__(self, relay: AgentRelay, sender_name: str):
        self.relay = relay
        self.sender_name = sender_name

    async def send_agent_message(self, receiver: str, content: str, mirror: bool = True) -> ToolResponse:
        """
        向其他 Agent 发送消息。

        Args:
            receiver: 目标 Agent 名称（如 ConceptAgent / ProduceAgent）。
            content: 发送内容。
            mirror: 是否同步到飞书（默认 True）。
        """
        if not receiver or not content:
            return ToolResponse(content=[TextBlock(type="text", text="❌ receiver/content 不能为空")])

        try:
            response = await self.relay.send(self.sender_name, receiver, content, mirror=mirror)
            response_text = ""
            if response is not None:
                _, response_text = normalize_message_content(response.content)

            if response_text:
                return ToolResponse(content=[TextBlock(
                    type="text",
                    text=(
                        f"✅ 已发送给 {receiver}\n\n"
                        f"【{receiver} 回复】\n{response_text}"
                    ),
                )])

            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 已发送给 {receiver}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 发送失败: {e}")])
