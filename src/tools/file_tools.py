from agentscope.tool import ToolResponse
from agentscope.message import TextBlock
from src.core.file_manager import FileManager


class FileTool:
    """
    [文件工具] Interface Layer
    Agent 在场地中活动的唯一接口。
    """

    def __init__(self):
        # 实例化全能管家
        self.manager = FileManager()

    # =========================================
    # 🏗️ 场地初始化 (Stage Setup)
    # =========================================

    def init_project_structure(self, project: str) -> ToolResponse:
        """[初始化] 创建项目根目录"""
        try:
            path = self.manager.init_project(project)
            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 项目场地已就绪: {path}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def init_scene_structure(self, project: str, scene: str) -> ToolResponse:
        """[初始化] 创建场景目录 (含Concept区)"""
        try:
            path = self.manager.init_scene(project, scene)
            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 场景场地已就绪: {path}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def init_design_structure(self, project: str, category: str, name: str) -> ToolResponse:
        """
        [统一初始化] 创建视觉资产目录。
        路径逻辑: /app/production/{project}/_Design/{category}/{name}

        Args:
            project: 项目名
            category: 类别 (character, prop, vehicle, environment)
            name: 资产名 (snake_case)
        """
        # 强制小写
        cat_folder = category.lower()
        name_folder = name.lower()

        # 你的 FileManager 底层逻辑
        # 结果示例: /app/production/MyFilm/_Design/character/neo
        try:
            relative_path = f"{project}/_Design/{cat_folder}/{name_folder}"
            full_path = self.manager.init_directory(relative_path)
            return ToolResponse(content=[TextBlock(type="text", text=full_path)])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Init failed: {e}")])

    def init_character_structure(self, project: str, name: str) -> ToolResponse:
        """[初始化] 创建角色目录"""
        try:
            path = self.manager.init_character(project, name)
            return ToolResponse(content=[TextBlock(type="text", text=path)])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def init_shot_structure(self, project: str, scene: str, shot: str, version: int) -> ToolResponse:
        """[初始化] 创建镜头版本目录"""
        try:
            path = self.manager.init_shot(project, scene, shot, version)
            return ToolResponse(content=[TextBlock(type="text", text=path)])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def read_image_as_url(self, local_path: str) -> ToolResponse:
        """[查看] 读取本地图片 (自动转为云端链接给 Agent 看)"""
        try:
            if local_path and (local_path.startswith("http://") or local_path.startswith("https://")):
                return ToolResponse(content=[TextBlock(type="text", text=local_path)])
            url = self.manager.get_file_url(local_path)
            if url:
                return ToolResponse(content=[TextBlock(type="text", text=url)])
            else:
                return ToolResponse(content=[TextBlock(type="text", text="❌ 文件不存在或同步失败")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])