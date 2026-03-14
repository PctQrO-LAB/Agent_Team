from typing import Optional

from agentscope.tool import ToolResponse
from agentscope.message import TextBlock
from agentscope.pipeline import MsgHub
from agentscope.message import Msg

from src.utils.message_utils import normalize_message_content

from src.core.agent_relay import AgentRelay


class AgentRelayTool:
    """
    供 LLM 调用的 Agent 间通信工具。
    """

    def __init__(self, relay: AgentRelay, sender_name: str):
        self.relay = relay
        self.sender_name = sender_name

    async def broadcast_message(self, content: str, mirror: bool = True) -> ToolResponse:
        """
        [广播能力]向所有其他 Agent 广播消息。在需要广播的时候广播这些信息。

        Args:
            content: 发送内容。
            mirror: 是否同步到飞书（默认 True）。
        """
        if not content:
            return ToolResponse(content=[TextBlock(type="text", text="❌ content 不能为空")])

        try:
            # 收集所有其他参与的 Agent
            participants = [agent for name, agent in self.relay.agents.items() if name != self.sender_name]
            if not participants:
                return ToolResponse(content=[TextBlock(type="text", text="❌ 没有其他 Agent 可供广播")])

            msg = Msg(name=self.sender_name, content=content, role="assistant")

            # 使用 MsgHub 异步上下文管理器广播消息，同一个 MsgHub 中的智能体会自动接收其它参与者返回的消息
            async with MsgHub(participants=participants, announcement=msg) as hub:
                pass

            if mirror and self.relay.mirror_chat_id:
                manager = None
                sender_agent = self.relay.agents.get(self.sender_name)
                if sender_agent:
                    manager = getattr(sender_agent, "manager", None)

                if manager:
                    mirror_text = f"📢 **{self.sender_name} (广播) → Everyone**\n{content}"
                    import asyncio
                    asyncio.create_task(manager.reply(self.relay.mirror_chat_id, mirror_text, receive_id_type=self.relay.mirror_receive_id_type))

            return ToolResponse(content=[TextBlock(type="text", text="✅ 消息已广播给所有其他 Agent")])
        except Exception as e:
            import traceback
            traceback.print_exc()
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 广播失败: {e}")])

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
