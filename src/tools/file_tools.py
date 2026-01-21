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

    def init_character_structure(self, project: str, name: str) -> ToolResponse:
        """[初始化] 创建角色目录"""
        try:
            path = self.manager.init_character(project, name)
            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 角色场地已就绪: {path}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def init_shot_structure(self, project: str, scene: str, shot: str, version: int) -> ToolResponse:
        """[初始化] 创建镜头版本目录"""
        try:
            path = self.manager.init_shot(project, scene, shot, version)
            return ToolResponse(content=[TextBlock(type="text", text=path)])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    # =========================================
    # 🎬 场地活动 (Actions)
    # =========================================

    def save_prompt_file(self, dir_path: str, content: dict) -> ToolResponse:
        """[存档] 保存 Prompt JSON"""
        try:
            path = self.manager.save_json(dir_path, "prompt.json", content)
            return ToolResponse(content=[TextBlock(type="text", text=f"✅ Prompt 已归档: {path}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def save_image_file(self, dir_path: str, file_name: str, image_data: str) -> ToolResponse:
        """[存档] 保存图片 (Base64)"""
        try:
            path = self.manager.save_image(dir_path, file_name, image_data)
            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 图片已归档: {path}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def read_image_as_url(self, local_path: str) -> ToolResponse:
        """[查看] 读取本地图片 (自动转为云端链接给 Agent 看)"""
        try:
            url = self.manager.get_file_url(local_path)
            if url:
                return ToolResponse(content=[TextBlock(type="text", text=url)])
            else:
                return ToolResponse(content=[TextBlock(type="text", text="❌ 文件不存在或同步失败")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])