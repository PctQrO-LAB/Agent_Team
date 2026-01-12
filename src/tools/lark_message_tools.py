import lark_oapi as lark
from lark_oapi.api.im.v1 import *
import base64
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock

class LarkMessageTool:
    """
    飞书消息资源工具
    用于下载聊天过程中产生的图片、文件等临时资源。
    """
    def __init__(self, app_id: str, app_secret: str):
        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()

    def download_image(self, message_id: str, image_key: str) -> ToolResponse:
        """
        下载飞书聊天中的图片，并转为 Base64 编码（供 VLM 模型使用）。
        Args:
            message_id: 消息 ID (必须提供，用于权限验证)
            image_key: 图片的 Key
        """
        try:
            # 构造请求：获取消息中的资源
            req = GetMessageResourceRequest.builder() \
                .message_id(message_id) \
                .file_key(image_key) \
                .type("image") \
                .build()

            # 发起下载
            resp = self.client.im.v1.message_resource.get(req)

            if not resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 图片下载失败: {resp.msg} (Code: {resp.code})")])

            # 读取二进制流并转 Base64
            image_bytes = resp.file.read()
            base64_str = base64.b64encode(image_bytes).decode('utf-8')

            # 返回结果：为了防止 Log 爆炸，我们这里只返回部分信息，
            # 真正的 Base64 数据通常会被 Agent 隐式处理，或者我们通过特殊标记返回
            return ToolResponse(content=[
                TextBlock(type="text", text=f"✅ 图片已下载 (Size: {len(image_bytes)} bytes)"),
                # 这里我们把 Base64 放在 content 里，AgentScope 的模型 wrapper 需要能识别这种格式
                # 或者你可以直接返回 image_url 如果你的模型支持 URL
                TextBlock(type="image", content=base64_str)
            ])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 系统异常: {str(e)}")])