import os
import json
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock


class FileTool:
    """
    剧组文件系统管理工具 (Physical Layer)

    该工具负责管理本地文件系统中的剧组资产目录结构，强制执行标准化的命名规范，
    并处理文件的实际写入操作。它是智能体与物理存储之间的交互接口。

    Attributes:
        ROOT_PATH (str): 容器内的挂载根目录，对应宿主机的剧组素材目录。
    """

    ROOT_PATH = "/app/production"

    def init_shot_structure(self, project: str, scene: str, shot: str, version: int) -> ToolResponse:
        """
        [初始化] 创建镜头对应的版本文件夹结构。

        根据剧组的标准目录规范（Project/Scene/Shot/Version），在物理磁盘上递归创建
        对应的文件夹层级。如果目标文件夹已存在，则静默成功并返回路径。

        Args:
            project (str): 项目名称（如 "WanderingEarth3"）。
            scene (str): 场次代码（如 "Scene_01"）。
            shot (str): 镜头代码（如 "Shot_05"）。
            version (int): 版本号（如 1）。

        Returns:
            ToolResponse: 包含目标目录绝对路径的响应对象。
                          Content 示例: "/app/production/WanderingEarth3/Scene_01/Shot_05/v1"
        """
        try:
            # 构造路径: /Root/Project/Scene/Shot/v1
            dir_path = os.path.join(self.ROOT_PATH, project, scene, shot, f"v{version}")

            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                return ToolResponse(content=[TextBlock(type="text", text=dir_path)])
            else:
                return ToolResponse(content=[TextBlock(type="text", text=dir_path)])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 创建目录失败: {e}")])

    def save_prompt_file(self, dir_path: str, content: dict) -> ToolResponse:
        """
        [写入] 将 Prompt 数据保存为 JSON 文件。

        将包含提示词信息的字典序列化为 JSON 格式，并写入指定目录下的 `prompt.json` 文件中。
        该方法包含安全检查，防止写入到 ROOT_PATH 之外的非法路径。

        Args:
            dir_path (str): 目标文件夹的绝对路径（必须以 ROOT_PATH 开头）。
            content (dict): 要保存的数据字典，通常包含 description, model, params 等字段。

        Returns:
            ToolResponse: 操作结果消息。
                          成功示例: "✅ 文件已写入: /app/production/.../prompt.json"
                          失败示例: "❌ 拒绝操作：禁止写入规定目录以外的路径。"
        """
        try:
            # 1. 路径校验
            if not dir_path.startswith(self.ROOT_PATH):
                return ToolResponse(content=[TextBlock(type="text", text="❌ 拒绝操作：禁止写入规定目录以外的路径。")])

            file_path = os.path.join(dir_path, "prompt.json")

            # 2. 写入文件
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2)

            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 文件已写入: {file_path}")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 写入失败: {e}")])