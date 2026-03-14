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
        asset_id: str,
        author_agent: Optional[str] = None,
        reference_images: Optional[List[str]] = None,
        mode: str = "text2img",
        describe: Optional[str] = None,
    ) -> ToolResponse:
        """
        [委托生成] 发送生图指令。

        Args:
            prompt: 英文提示词。
            asset_id: 资产ID (如 p01-sc01-en01)。
            author_agent: 发起委托的作者/智能体名称 (可选)。
            reference_images: 参考图 URL 列表 (可选，多图参考时传入)。
            mode: 生成模式 (text2img / img2img / multi_ref)。
            describe: 对该资产的描述信息（如角色名称，特征等可选附加信息）。
        """
        if not self.webhook_url:
            return ToolResponse(content=[TextBlock(type="text", text="❌ Error: N8N_IMAGE_WEBHOOK_URL 未配置。")])
        
        import re
        import sqlite3
        import os
        from datetime import datetime
        
        # 1. 拆解 asset_id，推导物理路径
        parts = asset_id.split("-")
        if len(parts) >= 3:
            project = parts[0]
            scene_str = parts[1]
            last_part = parts[2]
            
            # 使用正则分离类别和编号 (例如 en01 -> en, 01)
            match = re.match(r"^([A-Za-z]+)\d+$", last_part)
            category_code = match.group(1) if match else "unknown"
            
            # 内部映射，将前缀映射到_文件夹名称
            cat_map = {
                "en": "_Concept",
                "ch": "_Character",
                "pr": "_Prop",
                "sh": "Shots"  # 后面特殊处理
            }
            folder_name = cat_map.get(category_code, "_Concept")
            
            # 基础路径构成
            base_dir = f"/app/production/{project}/{project}-{scene_str}/{folder_name}"
            
        else:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: asset_id 格式不符要求(需如 p01-sc01-en01): {asset_id}")])
            
        # 2. 查询 SQLite 获取最新 version，或插入新记录
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "shared", "agent_shared.db")
        new_version = 1
        
        # 预先计算 target_path -> /app/production/.../xxx_v1.jpg
        # 但如果是新版本，这会在下面更新
        
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT version FROM design_assets WHERE project = ? AND category = ? AND uid = ?", (project, category_code, asset_id))
            row = cursor.fetchone()
            
            db_describe = describe if describe else prompt
            if row:
                new_version = row["version"] + 1
                target_path = f"{base_dir}/{asset_id}_v{new_version}.jpg"
                cursor.execute(
                    "UPDATE design_assets SET version = ?, updated_at = CURRENT_TIMESTAMP, image_path = ?, describe = ? WHERE project = ? AND category = ? AND uid = ?",
                    (new_version, target_path, db_describe, project, category_code, asset_id)
                )
            else:
                target_path = f"{base_dir}/{asset_id}_v1.jpg"
                cursor.execute(
                    """INSERT INTO design_assets 
                       (project, category, uid, describe, image_path, version) 
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (project, category_code, asset_id, db_describe, target_path, 1)
                )
            
            conn.commit()
            conn.close()
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Database Error: {e}")])
            
        # 4. 组装 Payload 发给 n8n
        payload = {
            "prompt": prompt,
            "target_path": target_path,
            "mode": mode,
            "asset_id": asset_id,        # 传送 metadata
        }

        if author_agent:
            payload["author_agent"] = author_agent
            
        if describe:
            payload["describe"] = describe

        if reference_images:
            payload["reference_images"] = reference_images

        try:
            # 发送请求
            import requests # fallback
            resp = requests.post(self.webhook_url, json=payload, timeout=10)

            if resp.status_code == 200:
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 委托已发送 (n8n Webhook)。\nPrompt: {prompt[:50]}...\nPath: {target_path}\nDB自动登记! Version: {new_version}")])
            else:
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 平台拒收: {resp.text}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 连接异常: {e}")])

    def generate_image_batch(
        self,
        asset_ids: List[str],
        author_agent: Optional[str] = None,
        mode: str = "text2img"
    ) -> ToolResponse:
        """
        [批量委托生成图片] 发送并行的批量多生图指令。
        要求：如果在一次思考中决定生成多个图像，调用的 agent 需要提前在数据库中（通过 save_design_asset ）把基本信息登记好。
        工具会自动从数据库设计资产表(design_assets)中提取对应的 prompt 和 describe，打包发送给 n8n。

        Args:
            asset_ids: 已登记的资产ID列表 (如 ["p01-sc01-en01", "p01-sc01-en02", "p01-ch01"])。
            author_agent: 发起委托的智能体名称。
            mode: 生成模式 (text2img / img2img)。
        """
        
        import os
        batch_url = os.environ.get("N8N_IMAGE_BATCH_WEBHOOK_URL", self.webhook_url)
        if not batch_url:
            return ToolResponse(content=[TextBlock(type="text", text="❌ Error: Webhook未配置。")])
        
        import re
        import sqlite3
        import os
        
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "shared", "agent_shared.db")
        tasks = []
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            for asset_id in asset_ids:
                parts = asset_id.split("-")
                if len(parts) >= 3:
                    project = parts[0]
                    scene_str = parts[1]
                    last_part = parts[2]
                elif len(parts) == 2:
                    project = parts[0]
                    scene_str = ""
                    last_part = parts[1]
                else:
                    print(f"⚠️ 解析跳过: {asset_id} (格式不符)")
                    continue
                    
                match = re.match(r"^([A-Za-z]+)\d+$", last_part)
                category_code = match.group(1).lower() if match else "en"
                
                if len(parts) >= 3:
                    cat_map = {"en": "_Concept", "ch": "_Character", "pr": "_Prop", "sh": "Shots"}
                    folder_name = cat_map.get(category_code, "_Concept")
                    base_dir = f"/app/production/{project}/{project}-{scene_str}/{folder_name}"
                else:
                    if category_code == "ch":
                        base_dir = f"/app/production/{project}/_Design/character/{asset_id.lower()}"
                    elif category_code == "pr":
                        base_dir = f"/app/production/{project}/_Design/prop/{asset_id.lower()}"
                    else:
                        base_dir = f"/app/production/{project}/_Design/environment/{asset_id.lower()}"
                        
                cursor.execute("SELECT * FROM design_assets WHERE uid = ?", (asset_id,))
                row = cursor.fetchone()
                
                if row:
                    new_version = (row["version"] if row["version"] else 1) + 1
                    target_path = f"{base_dir}/{asset_id}_v{new_version}.jpg"
                    
                    prompt_val = row["prompt_path"]
                    describe_val = row["describe"]
                    final_prompt = prompt_val if prompt_val and len(str(prompt_val)) > 5 else describe_val
                    if not final_prompt: 
                        final_prompt = f"A high quality image of {asset_id}"
                        
                    cursor.execute(
                        "UPDATE design_assets SET version = ?, updated_at = CURRENT_TIMESTAMP, image_path = ? WHERE uid = ?",
                        (new_version, target_path, asset_id)
                    )
                    
                    tasks.append({
                        "asset_id": asset_id,
                        "describe": describe_val if describe_val else final_prompt,
                        "prompt": final_prompt,
                        "target_path": target_path
                    })
                else:
                    # ✅ Fallback: 尝试在 scenes 表中查找 (ConceptAgent 生成场景时)
                    cursor.execute("SELECT * FROM scenes WHERE uid = ?", (asset_id,))
                    scene_row = cursor.fetchone()
                    if scene_row:
                        new_version = (scene_row["version"] if scene_row["version"] else 1) + 1
                        
                        # 构建目标路径 (场景概念图)
                        concept_dir = f"/app/production/{project}/{asset_id}/_Concept"
                        target_path = f"{concept_dir}/{asset_id}_v{new_version}.jpg"
                        
                        # 兼容无 describe/prompt_path 的场景表：使用 world_prompt、mood 等拼接
                        world = scene_row["world_prompt"]
                        mood = scene_row["mood"]
                        elements = scene_row["elements"]
                        
                        parts = [p for p in [world, mood, elements] if p and isinstance(p, str) and len(p.strip()) > 0]
                        final_prompt = ", ".join(parts) if parts else f"A scene design of {asset_id}"
                        describe_val = scene_row["world_prompt"] if scene_row["world_prompt"] else f"Scene {asset_id} Concept"
                        
                        # 更新 version
                        cursor.execute("UPDATE scenes SET version = ?, updated_at = CURRENT_TIMESTAMP WHERE uid = ?", (new_version, asset_id))
                        
                        tasks.append({
                            "asset_id": asset_id,
                            "describe": describe_val,
                            "prompt": final_prompt,
                            "target_path": target_path
                        })
                    else:
                        print(f"⚠️ 遗漏资产: 尚未在数据库找到 `{asset_id}` 的登记记录，跳过该项。")
                    
            conn.commit()
            conn.close()
            
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Database Error: {e}")])
            
        if not tasks:
            return ToolResponse(content=[TextBlock(type="text", text="❌ 批处理中止：传入的资产没有一个能在数据库找到。请先用 save_design_asset 或类似工具登记信息。")])
            
        payload = {
            "batch": True,
            "mode": mode,
            "author_agent": author_agent,
            "tasks": tasks
        }

        try:
            import requests # fallback
            resp = requests.post(batch_url, json=payload, timeout=20)
            if resp.status_code == 200:
                summary = "\n".join([f"- {t['asset_id']} (Update to v{t['target_path'].split('_v')[-1].split('.')[0]})" for t in tasks])
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 批量委托已发送 (n8n Webhook)。\n共提交 {len(tasks)} 个任务:\n{summary}\n数据库状态已同步。")])
            else:
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 批量委托发送被平台拒收: {resp.text}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 批量发送连接异常: {e}")])

    def generate_storyboard_batch(
        self,
        project: str,
        scene: str,
        scene_design_ids: Optional[List[str]] = None,
        other_design_ids: Optional[List[str]] = None
    ) -> ToolResponse:
        """
        [批量分镜委托] 读取数据库获取场次的分镜列表和文件路径，并将本地设计图转为云端 URL，最后打包发送给 N8N。

        Args:
            project: 项目名称 (如 "MyFilm")。
            scene: 场号 (如 "1", "2A")，用于在 shots 表中查询。
            scene_design_ids: ID列表(尤指场景概念环境 ID) 场景环境设计图路径列表。
            other_design_ids: ID列表(角色/道具等 ID) 角色、道具等其他设计图路径列表。
        """
        # 1. 获取 Webhook URL
        webhook_url = os.environ.get("N8N_SHOT_BATCH_WEBHOOK_URL")
        if not webhook_url:
            return ToolResponse(content=[TextBlock(type="text", text="❌ Error: 环境变量 N8N_SHOT_BATCH_WEBHOOK_URL 未配置。")])

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
                cursor.execute("SELECT id FROM scenes WHERE project = ? AND uid = ?", (project, scene))
                scene_row = cursor.fetchone()
                if scene_row and scene_row['uid']:
                    scene_root_path = f'/app/production/{project}/{project}-{scene}/Shots'
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

        # 3. 拦截ID转化为物理路径并处理参考图 (ID -> Local Path -> OSS URL)
        scene_urls = {}
        other_urls = {}
        
        try:
            # 获取数据库路径并执行查询映射
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.path.join(base_dir, "data", "shared", "agent_shared.db")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            def map_ids_to_paths(asset_ids):
                paths = []
                if not asset_ids: return paths
                for aid in asset_ids:
                    cursor.execute("SELECT image_path FROM design_assets WHERE uid = ?", (aid,))
                    row = cursor.fetchone()
                    if row and row['image_path']:
                        paths.append(row['image_path'])
                    else:
                        print(f"⚠️ Warning: DB missing image_path for {aid}")
                return paths
                
            scene_design_files = map_ids_to_paths(scene_design_ids)
            other_design_files = map_ids_to_paths(other_design_ids)
            conn.close()
            
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