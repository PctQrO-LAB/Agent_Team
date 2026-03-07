import os
import sqlite3
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
        """[初始化] 创建场景目录 (含Concept区)，并记录路径到数据库。使用时必须以严格编号交互。"""
        
        # 强制格式化机制：如果传了 sc01，强制补齐为 p01-sc01
        import re
        if scene and not scene.startswith(project):
            # 将多余的杠去掉重组
            clean_scene = scene.lstrip('-')
            scene = f"{project}-{clean_scene}"
            
        try:
            path = self.manager.init_scene(project, scene)
            concept_path = f"{path}/_Concept"
            
            # --- Auto-Record to DB ---
            try:
                import os, sqlite3
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                db_path = os.path.join(base_dir, "data", "shared", "agent_shared.db")
                
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE scenes SET file_path = ? WHERE project = ? AND scene = ?", (path, project, scene))
                    if cursor.rowcount == 0:
                        cursor.execute("INSERT INTO scenes (project, scene, file_path) VALUES (?, ?, ?)", (project, scene, path))
                    conn.commit()
            except Exception as db_e:
                print(f"⚠️ Warning: Failed to record scene path to DB: {db_e}")

            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 场景场地已就绪。\n📂 场景根目录: {path}\n💡 【强调】请务必将该场景的概念图(Concept)生成至此专属路径: {concept_path}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def init_design_structure(self, project: str, category: str, name: str) -> ToolResponse:
        """
        [统一初始化] 创建视觉资产目录。
        注意：这里的 name 必须是经过 note_tools 注册后派发的绝对ID（例如: p01-sc03-en01 或 p01-ch01）
        路径逻辑: /app/production/{project}/_Design/{category}/{name}

        Args:
            project: 项目名 (如 p01)
            category: 类别规范 (en, ch, pr)
            name: 资产严格编号 (如 p01-sc03-en01)
        """
        # 严格防御性映射和清洗
        PREFIX_MAP = {
            "environment": "en", "en": "en",
            "character": "ch", "ch": "ch",
            "prop": "pr", "pr": "pr"
        }
        cat_folder = PREFIX_MAP.get(category.lower(), category.lower())
        name_folder = name.lower()

        # 你的 FileManager 底层逻辑
        # 结果示例: /app/production/p01/_Design/en/p01-sc03-en01
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
                # 尝试探测一下文件是否存在，给出更具体的建议
                import os
                exists = os.path.exists(local_path) if local_path else False
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 文件转链接失败。\n请求路径: '{local_path}'\n本地存在: {exists}\n建议: 请检查路径拼写，或确认 Docker 卷挂载正常。确保 oss 已配置。")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])