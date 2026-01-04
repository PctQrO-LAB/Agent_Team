import os
import base64
import lark_oapi as lark
from lark_oapi.api.drive.v1 import *
from typing import List, Dict, Optional


class LarkDriveTool:
    """
    飞书云空间工具 (Drive Tool)
    基于官方文档实现：下载、上传、列表查询、搜索
    """

    def __init__(self, app_id: str, app_secret: str):
        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()

    # =================================================
    # 1. 👁️ 视觉能力：读取图片 (对应文档 "下载文件")
    # =================================================
    def read_image_as_base64(self, file_token: str) -> Optional[str]:
        """
        下载并读取图片内容，转为 Base64 供多模态模型使用。
        对应文档 API: GET .../files/:file_token/download
        """
        try:
            # 构造下载请求
            req = DownloadFileRequest.builder().file_token(file_token).build()

            # 发起调用
            resp = self.client.drive.v1.file.download(req)

            if not resp.success():
                print(f"❌ 图片下载失败: {resp.msg} (Code: {resp.code})")
                return None

            # 读取二进制流
            image_bytes = resp.file.read()

            # 转 Base64
            base64_str = base64.b64encode(image_bytes).decode('utf-8')
            return base64_str

        except Exception as e:
            print(f"❌ 读取异常: {e}")
            return None

    # =================================================
    # 2. 📂 浏览能力：列出文件夹内容 (对应文档 "获取文件夹中的文件清单")
    # =================================================
    def list_images_in_folder(self, folder_token: str) -> str:
        """
        列出指定文件夹下的所有图片文件。
        对应文档 API: GET .../files?folder_token=xxx (List Interface)
        """
        try:
            # 构造请求：列出文件
            req = ListFileRequest.builder() \
                .folder_token(folder_token) \
                .page_size(50) \
                .build()

            resp = self.client.drive.v1.file.list(req)

            if not resp.success():
                return f"❌ 获取列表失败: {resp.msg}"

            files = resp.data.files or []
            if not files:
                return "📂 该文件夹为空。"

            # 过滤图片 (根据文件类型 type='file' 且文件名后缀)
            image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp']
            image_list = []

            for f in files:
                # 飞书 API 返回的 type: 'file' (文件), 'doc' (文档), 'folder' (文件夹)
                if f.type == 'file':
                    # 简单通过后缀判断是否为图片
                    if any(f.name.lower().endswith(ext) for ext in image_extensions):
                        image_list.append(f"- 🖼️ {f.name} (Token: {f.token})")
                    else:
                        # 也可以列出其他文件，但做个标记
                        image_list.append(f"- 📄 {f.name} (Token: {f.token})")
                elif f.type == 'folder':
                    image_list.append(f"- 📁 [文件夹] {f.name} (Token: {f.token})")

            return "📂 **文件夹内容清单**:\n" + "\n".join(image_list)

        except Exception as e:
            return f"❌ 系统异常: {e}"

    # =================================================
    # 3. 🔍 检索能力：查找文件 (对应文档 "搜索文件")
    # =================================================
    def search_file_by_name(self, query: str) -> str:
        """
        全盘搜索文件。
        对应文档 API: POST .../search/object
        """
        try:
            # 这里的 request_body 结构需参考 search/object 的具体定义
            # 注意：Search 接口通常在 suite 或 drive 模块下
            # 这里演示使用 requests 封装或者 SDK 的 search 方法
            # 由于 SDK 版本差异，这里用最通用的 Drive List 配合 Python 过滤 (如果是在特定文件夹下)
            # 或者使用 search 模块（如果 SDK 支持）

            # --- 方案 A: 推荐 Agent 养成良好习惯，只在工作目录下查找 ---
            # (这里暂时返回提示，建议配合 list_images_in_folder 使用)
            return "💡 建议先使用 `list_images_in_folder` 查看指定目录。全局搜索耗时较长。"

            # 若必须全局搜索，需调用 client.search.v2... (需要确认 SDK 版本支持)

        except Exception as e:
            return f"❌ 搜索失败: {e}"

    # =================================================
    # 4. 💾 管理能力：上传文件 (对应文档 "上传文件")
    # =================================================
    def upload_image(self, local_path: str, parent_folder_token: str) -> str:
        """
        上传本地图片到云空间。
        对应文档 API: POST .../files/upload_all
        """
        if not os.path.exists(local_path):
            return "❌ 本地文件不存在"

        try:
            file_name = os.path.basename(local_path)
            file_size = os.path.getsize(local_path)

            with open(local_path, "rb") as f:
                req_body = UploadAllFileRequestBody.builder() \
                    .file_name(file_name) \
                    .parent_type("explorer") \
                    .parent_node(parent_folder_token) \
                    .size(file_size) \
                    .file(f) \
                    .build()

                req = UploadAllFileRequest.builder().request_body(req_body).build()
                resp = self.client.drive.v1.file.upload_all(req)

            if not resp.success():
                return f"❌ 上传失败: {resp.msg}"

            return f"✅ 图片已上传: {file_name}\n🔗 Token: {resp.data.file_token}"

        except Exception as e:
            return f"❌ 上传异常: {e}"

    # =================================================
    # 🛠️ 辅助工具
    # =================================================
    def get_token_from_url(self, url: str) -> str:
        """从 URL 提取 Token (支持 file/box/folder)"""
        if "/file/" in url:
            return url.split("/file/")[1].split("/")[0].split("?")[0]
        elif "/folder/" in url:
            return url.split("/folder/")[1].split("/")[0].split("?")[0]
        return url