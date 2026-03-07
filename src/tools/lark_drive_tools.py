import os
import base64
import requests
import lark_oapi as lark
from lark_oapi.api.drive.v1 import *
from lark_oapi.api.docx.v1 import *
from typing import List, Dict, Optional

from agentscope.tool import ToolResponse
from agentscope.message import TextBlock


class LarkDriveTool:
    """
    飞书云空间工具 (Drive Tool)
    精简版：仅保留文件列表获取与文档读取能力
    """

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        
        # 0. 验证 Token (按照用户要求，显式获取 tenant_access_token)
        self.token_info = self._get_tenant_access_token()
        if self.token_info:
            print(f"✅ [LarkDriveTool] 成功获取/验证 tenant_access_token (有效期: {self.token_info.get('expire')}s)")
        else:
            print("❌ [LarkDriveTool] 获取 tenant_access_token 失败，请检查 APP_ID/SECRET")

        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()

    def _get_tenant_access_token(self) -> Optional[Dict]:
        """
        手动获取 tenant_access_token
        文档: https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal
        """
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        headers = {
            "Content-Type": "application/json; charset=utf-8"
        }
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=5)
            data = resp.json()
            if data.get("code") == 0:
                return data
            else:
                print(f"⚠️ Token Auth Failed: {data}")
                return None
        except Exception as e:
            print(f"⚠️ Token Auth Exception: {e}")
            return None

    # =================================================
    # 辅助工具
    # =================================================
    def get_token_from_url(self, url: str) -> str:
        """从 URL 提取 Token (支持 file/box/folder/docx)"""
        if "/file/" in url:
            return url.split("/file/")[1].split("/")[0].split("?")[0]
        elif "/folder/" in url:
            return url.split("/folder/")[1].split("/")[0].split("?")[0]
        elif "/docx/" in url:
            return url.split("/docx/")[1].split("/")[0].split("?")[0]
        return url

    # =================================================
    # 📖 阅读能力：获取文档纯文本
    # =================================================
    def read_document_content(self, document_id: str) -> ToolResponse:
        """
        获取指定文档 (docx) 的纯文本内容。
        对应文档 API: GET .../docx/:document_id
        """
        try:
            # 兼容处理：如果传入的是 URL，尝试提取 Token
            if "feishu.cn" in document_id:
                document_id = self.get_token_from_url(document_id)

            req = RawContentDocumentRequest.builder() \
                .document_id(document_id) \
                .build()

            resp = self.client.docx.v1.document.raw_content(req)

            if not resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ Read Failed: {resp.code} - {resp.msg}")])

            content = resp.data.content or "📄 [文档内容为空]"
            return ToolResponse(content=[TextBlock(type="text", text=content)])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Exception: {e}")])

    # =================================================
    # 📂 列表能力：获取文件夹内文件
    # =================================================
    def list_files_in_folder(self) -> ToolResponse:
        """
        获取项目“特定文件夹”下的文件列表（包含文档 ID/Token）。
        默认读取硬编码的文件夹: YpywfknyTlbqm2dC4L0cWDxrnF5
        """
        folder_token = "YpywfknyTlbqm2dC4L0cWDxrnF5"
        try:
            req = ListFileRequest.builder() \
                .folder_token(folder_token) \
                .page_size(50) \
                .build()

            resp = self.client.drive.v1.file.list(req)

            if not resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ API Error: {resp.code} - {resp.msg}")])

            if not resp.data.files:
                return ToolResponse(content=[TextBlock(type="text", text="📂 该文件夹为空。")])

            lines = [f"📂 文件夹内容 ({folder_token}):"]
            for f in resp.data.files:
                # 提取关键信息：Name, Type, Token, URL
                info = f"- [{f.type}] {f.name}\n  Token: {f.token}\n  URL: {f.url}"
                lines.append(info)
            
            return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

        except Exception as e:
            return f"❌ Exception: {e}"