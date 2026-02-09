import os
from typing import Dict, Optional

from agentscope.agent import ReActAgent
from agentscope.message import Msg

from src.utils.message_utils import normalize_message_content


class AgentRelay:
    """
    轻量级 Agent 间通信中继：
    - 直接在后端把消息转给目标 Agent
    - 可选把通信镜像到飞书指定会话
    """

    def __init__(
        self,
        agents: Optional[Dict[str, ReActAgent]] = None,
        mirror_chat_id: Optional[str] = None,
        mirror_receive_id_type: str = "chat_id",
    ):
        self.agents: Dict[str, ReActAgent] = agents or {}
        self.mirror_chat_id = mirror_chat_id or os.environ.get("AGENT_RELAY_CHAT_ID")
        self.mirror_receive_id_type = os.environ.get(
            "AGENT_RELAY_RECEIVE_ID_TYPE",
            mirror_receive_id_type,
        )

    def register(self, agent: ReActAgent):
        self.agents[agent.name] = agent

    async def send(self, sender: str, receiver: str, content: str, mirror: bool = True):
        if receiver not in self.agents:
            raise ValueError(f"Unknown receiver agent: {receiver}")

        if mirror:
            await self._mirror_message(sender, receiver, content)

        msg = Msg(name=sender, content=content, role="user")
        response = await self.agents[receiver](msg)

        if mirror:
            response_text = self._extract_text(response.content)
            if response_text:
                await self._mirror_message(receiver, sender, response_text)

        return response

    async def _mirror_message(self, sender: str, receiver: str, text: str):
        if not self.mirror_chat_id:
            return
        sender_agent = self.agents.get(sender)
        receiver_agent = self.agents.get(receiver)
        manager = getattr(sender_agent, "manager", None) or getattr(receiver_agent, "manager", None)
        if not manager:
            return
        mirror_text = f"🤝 **{sender} → {receiver}**\n{text}"
        await manager.reply(self.mirror_chat_id, mirror_text, receive_id_type=self.mirror_receive_id_type)

    @staticmethod
    def _extract_text(content):
        _, plain_text = normalize_message_content(content)
        return plain_text
