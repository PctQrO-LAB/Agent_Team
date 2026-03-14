import os
import sqlite3
from typing import Optional
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

    def init_workspace(self, asset_id: str) -> ToolResponse:
        """
        [初始化工作区] 统一的初始化路由工具。
        根据资产 ID 自动判定路径并创建物理文件夹，同时与 SQLite 数据库自动同步。
        
        Args:
            asset_id: 严格的全局资产编号 (如 p01, p01-sc01, p01-ch01, p01-sc01-en01, p01-sc01-sh01)。
        """
        import os
        import sqlite3
        import re
        
        try:
            parts = asset_id.split('-')
            project = parts[0]
            
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.path.join(base_dir, "data", "shared", "agent_shared.db")
            
            def get_db():
                conn = sqlite3.connect(db_path)
                return conn
                
            path = ""
            msg = ""
            
            if len(parts) == 1:
                # Project (e.g., p01)
                path = self.manager.init_project(project)
                msg = f"✅ 项目场地已就绪: {path}"
                
            elif len(parts) == 2:
                last_part = parts[1]
                match = re.match(r"^([a-zA-Z]+)(\d+)$", last_part)
                if match:
                    prefix = match.group(1).lower()
                    if prefix == "sc":
                        # Scene (e.g., p01-sc01)
                        scene_uid = f"{project}-{last_part}"
                        path = self.manager.init_scene(project, scene_uid)
                        conn = get_db()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE scenes SET file_path = ? WHERE project = ? AND uid = ?", (path, project, scene_uid))
                        if cursor.rowcount == 0:
                            cursor.execute("INSERT INTO scenes (project, uid, file_path) VALUES (?, ?, ?)", (project, scene_uid, path))
                        conn.commit()
                        conn.close()
                        msg = f"✅ 场景场地已就绪。\\n📂 场景根目录: {path}\\n💡 【提示】概念图(Concept)生成至此专属路径: {path}/_Concept"
                    elif prefix == "ch":
                        # Character (e.g., p01-ch01)
                        path = self.manager.init_character(project, asset_id)
                        msg = f"✅ 角色场地已就绪: {path}"
                    else:
                        raise ValueError(f"Unknown 2-part ID pattern: {asset_id}")
            elif len(parts) == 3:
                mid_part = parts[1]
                last_part = parts[2]
                match = re.match(r"^([a-zA-Z]+)(\d+)$", last_part)
                if match:
                    prefix = match.group(1).lower()
                    if prefix in ["en", "ch", "pr"]:
                        # Design Concept (e.g., p01-sc01-en01)
                        category = prefix
                        cat_folder = "environment" if category == "en" else ("character" if category == "ch" else "prop")
                        relative_path = f"{project}/_Design/{category}/{asset_id.lower()}"
                        path = self.manager.init_directory(relative_path)
                        msg = f"✅ 设计资产场地已就绪: {path}"
                    elif prefix == "sh":
                        # Shot (e.g., p01-sc01-sh01)
                        # Find latest version
                        conn = get_db()
                        cursor = conn.cursor()
                        scene = f"{project}-{mid_part}"
                        cursor.execute("SELECT MAX(version) FROM shots WHERE project=? AND scene=? AND shot=?", (project, scene, asset_id))
                        row = cursor.fetchone()
                        version = row[0] if (row and row[0] is not None) else 1
                        conn.close()
                        path = self.manager.init_shot(project, scene, asset_id, version)
                        msg = f"✅ 镜头场地已就绪 (v{version}): {path}"
                    else:
                        raise ValueError(f"Unknown prefix in 3-part ID: {prefix}")
            else:
                raise ValueError(f"Invalid asset_id format: {asset_id}")
                
            return ToolResponse(content=[TextBlock(type="text", text=msg)])
            
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error initializing workspace for {asset_id}: {e}")])

    # =========================================
    # 🔁 兼容层 (Compatibility APIs)
    # =========================================
    def init_scene_structure(self, project: str, scene: str) -> ToolResponse:
        """
        [兼容] 初始化场景结构。

        Args:
            project: 项目ID（如 p01）
            scene: 场景ID（如 sc01 或 p01-sc01）
        """
        if not project or not scene:
            return ToolResponse(content=[TextBlock(type="text", text="❌ project/scene 不能为空")])

        scene_id = scene if "-" in scene else f"{project}-{scene}"
        return self.init_workspace(scene_id)

    def init_shot_structure(self, project: str, scene: str, shot: str) -> ToolResponse:
        """
        [兼容] 初始化镜头结构。

        Args:
            project: 项目ID（如 p01）
            scene: 场景ID（如 sc01 或 p01-sc01）
            shot: 镜头ID（如 sh01 或 p01-sc01-sh01）
        """
        if not project or not scene or not shot:
            return ToolResponse(content=[TextBlock(type="text", text="❌ project/scene/shot 不能为空")])

        if shot.count("-") >= 2:
            shot_id = shot
        else:
            scene_part = scene.split("-")[-1] if "-" in scene else scene
            shot_part = shot if shot.startswith("sh") else f"sh{shot}"
            shot_id = f"{project}-{scene_part}-{shot_part}"

        return self.init_workspace(shot_id)

    def init_character_structure(self, project: str, character: str) -> ToolResponse:
        """
        [兼容] 初始化角色结构。

        Args:
            project: 项目ID（如 p01）
            character: 角色ID（如 ch01 或 p01-ch01）
        """
        if not project or not character:
            return ToolResponse(content=[TextBlock(type="text", text="❌ project/character 不能为空")])

        char_id = character if "-" in character else f"{project}-{character}"
        return self.init_workspace(char_id)

    def init_design_structure(
        self,
        asset_id: Optional[str] = None,
        project: Optional[str] = None,
        scene: Optional[str] = None,
        category: Optional[str] = None,
        uid: Optional[str] = None,
        name: Optional[str] = None,
    ) -> ToolResponse:
        """
        [兼容] 初始化设计资产结构。

        优先使用 `asset_id`/`uid`，例如：p01-sc01-en01。
        """
        final_id = asset_id or uid

        if not final_id and project and scene and category and name:
            scene_part = scene.split("-")[-1] if "-" in scene else scene
            final_id = f"{project}-{scene_part}-{category}{name}"

        if not final_id:
            return ToolResponse(content=[TextBlock(
                type="text",
                text=(
                    "❌ 缺少资产ID。请提供 asset_id/uid（如 p01-sc01-en01），"
                    "或提供 project+scene+category+name 进行拼装。"
                ),
            )])

        return self.init_workspace(final_id)

    def read_image_as_url(self, local_path: str) -> ToolResponse:
        """[查看] 读取本地图片 (自动转为云端链接给 Agent 看)"""
        try:
            if local_path and (local_path.startswith("http://") or local_path.startswith("https://")):
                return ToolResponse(content=[TextBlock(type="text", text=local_path)])
            url = self.manager.get_file_url(local_path)
            if url:
                return ToolResponse(content=[TextBlock(type="text", text=url)])
            else:
                # 尝试探测一下文件是否存在，给出更具体的建议
                import os
                exists = os.path.exists(local_path) if local_path else False
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 文件转链接失败。\n请求路径: '{local_path}'\n本地存在: {exists}\n建议: 请检查路径拼写，或确认 Docker 卷挂载正常。确保 oss 已配置。")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])