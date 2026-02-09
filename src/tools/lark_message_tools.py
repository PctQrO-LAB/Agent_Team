import os
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock


class LarkMessageTool:
    """
    飞书消息资源工具
    """

    def __init__(self, app_id: str, app_secret: str):
        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()

        self.image_save_dir = "/app/data/images"
        if not os.path.exists(self.image_save_dir):
            os.makedirs(self.image_save_dir, exist_ok=True)

    def download_image(self, message_id: str, image_key: str) -> ToolResponse:
        try:
            req = GetMessageResourceRequest.builder() \
                .message_id(message_id) \
                .file_key(image_key) \
                .type("image") \
                .build()

            resp = self.client.im.v1.message_resource.get(req)
            if not resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 下载失败: {resp.msg}")])

            # 保存文件
            file_name = f"{message_id}_{image_key}.jpg"
            file_path = os.path.join(self.image_save_dir, file_name)
            with open(file_path, "wb") as f:
                f.write(resp.file.read())

            # 🔥 关键：返回标准 ImageBlock，但 source.url 是本地路径
            # 这样 Agent 的记忆里只有这个短短的路径，不会爆炸
            return ToolResponse(content=[
                TextBlock(type="text", text=f"✅ 图片已就绪: {file_path}"),
                {
                    "type": "image",
                    "source": {
                        "type": "url",
                        "url": file_path  # 👈 本地路径，等待 ModelWrapper 处理
                    }
                }
            ])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 异常: {str(e)}")])