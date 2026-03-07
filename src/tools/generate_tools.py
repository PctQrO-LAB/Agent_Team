import requests
import json
import os
import sqlite3
from typing import List, Dict, Optional
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock
from src.core.file_manager import FileManager


class GenerationTool:
    """
    [生产委托工具] (简化版)
    职责：仅发送 Prompt 和 路径，无需关心发给谁。
    对接 n8n Webhook，用于替代 Anycross 飞书集成。
    """

    def __init__(self):
        # n8n Webhook 地址，兼容旧的 ANYCROSS_IMAGE_URL
        self.webhook_url = os.environ.get("N8N_IMAGE_WEBHOOK_URL") or os.environ.get("ANYCROSS_IMAGE_URL")

    def _paths_to_urls(self, file_manager: FileManager, paths: List[str]) -> Dict[str, str]:
        """[Helper] 将路径列表转换为 {文件名: URL} 字典，便于在工作流中通过名称识别"""
        url_map = {}
        if not paths:
            return url_map
            
        for path in paths:
            if not path: continue
            
            # 1. 提取名称 (文件名无后缀)
            try:
                file_name = os.path.basename(path)
                name_key = os.path.splitext(file_name)[0]
            except:
                name_key = "unknown_asset"

            # 2. 获取 URL
            final_url = None
            if path.startswith("http://") or path.startswith("https://"):
                 final_url = path
            else:
                 final_url = file_manager.get_file_url(path)

            if final_url:
                # 3. 处理重名: 如果 name 已存在，添加 _2, _3 后缀
                original_key = name_key
                counter = 1
                while name_key in url_map:
                    counter += 1
                    name_key = f"{original_key}_{counter}"
                
                url_map[name_key] = final_url
            else:
                print(f"⚠️ Warning: 无法获取文件 URL: {path}")
        return url_map

    def generate_image(
        self,
        prompt: str,
        target_path: str,
        author_agent: Optional[str] = None,
        reference_images: Optional[List[str]] = None,
        mode: str = "text2img",
    ) -> ToolResponse:
        """
        [委托生成] 发送生图指令。

        Args:
            prompt: 英文提示词。
            target_path: 本地保存路径。
            author_agent: 发起委托的作者/智能体名称 (可选)。
            reference_images: 参考图 URL 列表 (可选，多图参考时传入)。
            mode: 生成模式 (text2img / img2img / multi_ref)。
        """
        if not self.webhook_url:
            return ToolResponse(content=[TextBlock(type="text", text="❌ Error: N8N_IMAGE_WEBHOOK_URL 未配置。")])

        # 📦 Payload 精简了：只传生图需要的信息
        payload = {
            "prompt": prompt,
            "target_path": target_path,
            "mode": mode,
            # chat_id 被移除了，由飞书集成平台内部决定发给谁
        }

        if author_agent:
            payload["author_agent"] = author_agent

        if reference_images:
            payload["reference_images"] = reference_images

        try:
            # 发送请求
            resp = requests.post(self.webhook_url, json=payload, timeout=10)

            if resp.status_code == 200:
                return ToolResponse(content=[TextBlock(type="text",
                                                       text=f"✅ 委托已发送 (n8n Webhook)。\nPrompt: {prompt[:50]}...\nPath: {target_path}")])
            else:
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 平台拒收: {resp.text}")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 连接异常: {e}")])

    def generate_storyboard_batch(
        self,
        project: str,
        scene: str,
        scene_design_files: Optional[List[str]] = None,
        other_design_files: Optional[List[str]] = None
    ) -> ToolResponse:
        """
        [批量分镜委托] 读取数据库获取场次的分镜列表和文件路径，并将本地设计图转为云端 URL，最后打包发送给 N8N。

        Args:
            project: 项目名称 (如 "MyFilm")。
            scene: 场号 (如 "1", "2A")，用于在 shots 表中查询。
            scene_design_files: 场景环境设计图路径列表。
            other_design_files: 角色、道具等其他设计图路径列表。
        """
        # 1. 获取 Webhook URL
        webhook_url = os.environ.get("N8N_SHOT_WEBHOOK_URL")
        if not webhook_url:
            return ToolResponse(content=[TextBlock(type="text", text="❌ Error: 环境变量 N8N_SHOT_WEBHOOK_URL 未配置。")])

        # 2. 从 SQLite 读取分镜列表 和 Root Path
        shots_data = []
        scene_root_path = "/app/production/DEFAULT_FROM_TOOL" # Fallback

        try:
            # 路径推导: src/tools/generate_tools.py -> src/tools -> src -> root -> data/shared/agent_shared.db
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.path.join(base_dir, "data", "shared", "agent_shared.db")

            if not os.path.exists(db_path):
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: 共享数据库未找到: {db_path}")])

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 2.1 获取 Root Path
            try:
                cursor.execute("SELECT file_path FROM scenes WHERE project = ? AND scene = ?", (project, scene))
                scene_row = cursor.fetchone()
                if scene_row and scene_row['file_path']:
                    scene_root_path = scene_row['file_path']
                else:
                    print(f"⚠️ Warning: Database missing 'file_path' for {project}-{scene}. Using default fallback.")
            except Exception as e:
                print(f"⚠️ Warning: Failed to query scene path: {e}")

            # 2.2 查询该场次下的所有镜头
            cursor.execute("SELECT * FROM shots WHERE project = ? AND scene = ?", (project, scene))
            rows = cursor.fetchall()
            conn.close()

            if not rows:
                return ToolResponse(content=[TextBlock(type="text", text=f"⚠️ Warning: 在项目 '{project}' 第 '{scene}' 场中未找到任何镜头数据。请检查场号。")])

            # 转换为字典列表
            for row in rows:
                shots_data.append(dict(row))

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Database Error: {e}")])

        # 3. 处理参考图 (Local Path -> OSS URL)
        scene_urls = {}
        other_urls = {}
        
        try:
            # 动态实例化 FileManager 以复用其 OSS 逻辑
            file_manager = FileManager()
            
            if scene_design_files:
                scene_urls = self._paths_to_urls(file_manager, scene_design_files)
                
            if other_design_files:
                other_urls = self._paths_to_urls(file_manager, other_design_files)

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ OSS Upload Error: {e}")])

        # 4. 组装 Payload 并发送
        payload = {
            "project": project,
            "scene": scene,
            "scene_root_path": scene_root_path,
            "count": len(shots_data),
            "shots": shots_data,
            "scene_design_urls": scene_urls,
            "other_design_urls": other_urls,
            "timestamp": str(os.times())
        }

        try:
            resp = requests.post(webhook_url, json=payload, timeout=30)

            if resp.status_code == 200:
                return ToolResponse(content=[TextBlock(type="text", 
                    text=f"✅ 批量分镜任务已提交 (N8N)。\n"
                         f"Project: {project} | Scene: {scene}\n"
                         f"Root Path: {scene_root_path}\n"
                         f"Shots Count: {len(shots_data)}\n"
                         f"Scene Refs: {len(scene_urls)} | Other Refs: {len(other_urls)}")])
            else:
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 流程平台拒收 ({resp.status_code}): {resp.text}")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Webhook 连接异常: {e}")])