import sqlite3
import os
import time
import datetime
from typing import List, Dict, Optional

import json
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock
from src.core.file_manager import FileManager


class AgentNotebook:

    def __init__(self, agent_name: str, db_name: str = "agent_notes.db"):
        self.agent_name = agent_name

        # 1. 确定存储路径
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.data_dir = os.path.join(base_dir, "data")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        self.db_path = os.path.join(self.data_dir, db_name)

        self.file_manager = FileManager()

        # 2. 连接数据库
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # 3. 初始化表结构
        self._init_tables()

    def _init_tables(self):
        """初始化数据库表结构 (V2 白板模式)"""
        cursor = self.conn.cursor()

        # --- 1. Mementos (保持不变) ---
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS mementos
                       (
                           id         INTEGER PRIMARY KEY AUTOINCREMENT,
                           agent_name TEXT NOT NULL,
                           content    TEXT NOT NULL,
                           created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                       )
                       ''')

        # --- 2. Tasks (大改：以 lark_id 为核心) ---
        # 我们把 lark_id 设为 UNIQUE，这样数据库会自动帮我们防重
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS tasks
                       (
                           -- 虽然我们不查 id，但保留它作为主键通常是 SQLite 的最佳实践
                           id         INTEGER PRIMARY KEY AUTOINCREMENT,
                           agent_name TEXT NOT NULL,
                           -- 关键修改：添加 UNIQUE 约束，防止重复
                           lark_id    TEXT UNIQUE, 
                           content    TEXT NOT NULL,
                           status     TEXT      DEFAULT 'todo',
                           due_date   TEXT,
                           priority   INTEGER   DEFAULT 2,
                           created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           updated_at TIMESTAMP
                       )
                       ''')

        # --- 3. Calendars (大改：以 lark_event_id 为核心) ---
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS calendars
                       (
                           id            INTEGER PRIMARY KEY AUTOINCREMENT,
                           agent_name    TEXT NOT NULL,
                           -- 关键修改：添加 UNIQUE 约束
                           lark_event_id TEXT UNIQUE,
                           content       TEXT NOT NULL,
                           start_time    TEXT NOT NULL,
                           end_time      TEXT NOT NULL,
                           created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                       )
                       ''')

        # --- 4. Projects ---
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS projects
                       (
                           id         INTEGER PRIMARY KEY AUTOINCREMENT,
                           agent_name TEXT NOT NULL,
                           name       TEXT NOT NULL,
                           progress   TEXT,
                           updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                       )
                       ''')

        # --- 5. Patterns ---
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS patterns
                       (
                           id           INTEGER PRIMARY KEY AUTOINCREMENT,
                           agent_name   TEXT NOT NULL,
                           content      TEXT NOT NULL UNIQUE,
                           hit_count    INTEGER   DEFAULT 1,
                           is_promoted  BOOLEAN   DEFAULT 0,
                           last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                       )
                       ''')

        # --- 6. Resources ---
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS resources
                       (
                           id         INTEGER PRIMARY KEY AUTOINCREMENT,
                           agent_name TEXT NOT NULL,
                           file_name  TEXT NOT NULL,
                           file_type  TEXT,
                           file_path  TEXT NOT NULL,
                           tags       TEXT,
                           remark     TEXT,
                           created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                       )
                       ''')

        # === 7.镜头表 (shot) ===
        # 核心作用：连接“物理文件路径”与“逻辑状态”
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS production_assets
                       (
                           id              INTEGER PRIMARY KEY AUTOINCREMENT,
                           project         TEXT,
                           scene           TEXT,
                           shot            TEXT,
                           version         INTEGER,
                           prompt_path     TEXT, -- 存储 prompt.json 的路径
                           image_path      TEXT, -- 存储 render.jpg 的路径
                           status          TEXT, -- planning, generating, done, audited, rejected
                           audit_feedback  TEXT,

                           -- 🎥 影视工业字段
                           shot_size       TEXT, -- 景别 (Wide, Medium, Close-up...)
                           camera_angle    TEXT, -- 角度 (Eye-level, High angle...)
                           camera_movement TEXT, -- 运镜 (Static, Pan, Dolly...)
                           lighting        TEXT, -- 光照 (Natural, Rim light...)

                           updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           UNIQUE (project, scene, shot, version)
                       );
                       ''')

        # === 8. 提示词模版表 (prompt_templates) ===
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS prompt_templates
                       (
                           id         INTEGER PRIMARY KEY AUTOINCREMENT,
                           model_key  TEXT NOT NULL UNIQUE,
                           template   TEXT NOT NULL,
                           remarks    TEXT,
                           updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                       )
                       ''')

        # === 9. 场景设定表 (scenes) ===
        # 记录每个“场”的宏观设定
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS scenes
                       (
                           id            INTEGER PRIMARY KEY AUTOINCREMENT,
                           project       TEXT,
                           scene         TEXT,
                           world_prompt  TEXT,
                           elements      TEXT,
                           mood          TEXT,
                           color_tone    TEXT, -- 新增: 画面色调 (如: Cyberpunk Neon)
                           lighting_mood TEXT, -- 新增: 光影氛围 (如: Low Key Noir)
                           created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           UNIQUE (project, scene)
                       );
                       ''')

        # === 10. 视觉资产表 ===
        # 记录每个设计图
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS design_assets
                       (
                           id            INTEGER PRIMARY KEY AUTOINCREMENT,
                           project       TEXT NOT NULL,
                           name          TEXT NOT NULL, -- 资产名称 (snake_case)
                           category      TEXT NOT NULL, -- 类别: character, prop, vehicle, environment, costume

                           prompt_path   TEXT,          -- Prompt 文件路径
                           image_path    TEXT,          -- 图片路径

                           attributes    TEXT,          -- JSON字段，存储特有属性 (如角色的 personality, 道具的 material)
                           oss_url_cache TEXT,          -- 视觉缓存

                           status        TEXT,          -- planning, done, audited
                           remarks       TEXT,          -- 备注
                           created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           UNIQUE (project, name, category)
                       );
                       ''')
        self.conn.commit()

    def _execute_with_retry(self, sql: str, params: tuple = (), max_retries=5):
        """带重试机制的 SQL 执行器，防止死锁"""
        for i in range(max_retries):
            try:
                cursor = self.conn.cursor()
                cursor.execute(sql, params)
                self.conn.commit()
                return cursor
            except sqlite3.OperationalError as e:
                if "locked" in str(e):
                    time.sleep(0.1 * (i + 1))
                    if i == max_retries - 1:
                        print(f"❌ [DB Error] 数据库死锁，写入失败: {sql}")
                        raise e
                else:
                    raise e
            except Exception as e:
                print(f"❌ [DB Error] SQL: {sql} | Error: {e}")
                raise e

    def get_schema_prompt(self) -> str:
        """
        自动生成数据库结构描述，用于注入到 Agent 的 System Prompt 中。
        """
        cursor = self.conn.cursor()

        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence';")
        tables = cursor.fetchall()

        prompt_lines = ["\n## 📂 数据库结构 (用于 query_database 工具)"]
        prompt_lines.append("你可以使用 query_database(table_name, filter_conditions) 查询以下表格：")

        for table in tables:
            t_name = table[0]
            # 获取字段信息
            cursor.execute(f"PRAGMA table_info({t_name})")
            columns = [col[1] for col in cursor.fetchall()]  # col[1] 是字段名

            prompt_lines.append(f"- **{t_name}**: 包含字段 {columns}")

        return "\n".join(prompt_lines)

    # =================================================
    # 📝 日程与项目工具 (Schedule & Project) - 通用协作
    # 命名规范: save_task / get_tasks / del_task / save_project
    # =================================================
    def save_schedule(self, table_name: str, data: dict) -> ToolResponse:
        """
        [通用工具] 保存数据到指定表格。
        支持自动去重 (Upsert)：如果数据中包含唯一索引字段 (如 lark_id)，则更新旧记录；否则新建。

        Args:
            table_name: 目标表名 (如 'tasks', 'calendars')
            data: 要写入的字段字典，例如 {"content": "买奶茶", "lark_id": "xxx", "status": "todo"}
        """
        try:
            # 1. 安全检查：表是否存在
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table_name,))
            if not cursor.fetchone():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 错误：表 '{table_name}' 不存在。")])

            # 2. 自动补全基础字段 (如 updated_at)
            # 如果是 tasks 表，且没有提供 updated_at，自动补全
            if table_name == 'tasks' and 'updated_at' not in data:
                data['updated_at'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 3. 动态拼装 SQL (INSERT OR REPLACE)
            columns = list(data.keys())
            placeholders = ["?"] * len(columns)
            values = list(data.values())

            sql = f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"

            # 4. 执行
            self._execute_with_retry(sql, tuple(values))

            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 数据已保存至 '{table_name}'")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 保存失败: {e} (请检查字段名是否正确)")])

    def delete_schedule(self, table_name: str, conditions: dict) -> ToolResponse:
        """
        [通用工具] 从数据库删除指定记录。

        Args:
            table_name: 表名 (tasks, calendars, etc.)
            conditions: 删除条件字典，例如 {"id": 12} 或 {"lark_id": "xxx"}。
                        ⚠️ 警告：必须提供至少一个条件，禁止空条件删除全表！
        """
        if not conditions:
            return ToolResponse(
                content=[TextBlock(type="text", text="❌ 拒绝操作：必须提供删除条件 (conditions)，防止误删全表。")])

        try:
            # 1. 检查表是否存在 (安全检查)
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table_name,))
            if not cursor.fetchone():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 表 '{table_name}' 不存在")])

            # 2. 拼装 SQL
            clauses = []
            params = []
            for k, v in conditions.items():
                clauses.append(f"{k} = ?")
                params.append(v)

            where_sql = " AND ".join(clauses)
            sql = f"DELETE FROM {table_name} WHERE {where_sql}"

            # 3. 执行删除
            cursor = self._execute_with_retry(sql, tuple(params))

            if cursor.rowcount > 0:
                return ToolResponse(content=[
                    TextBlock(type="text", text=f"✅ 删除成功：已从 '{table_name}' 移除 {cursor.rowcount} 条记录。")])
            else:
                return ToolResponse(content=[
                    TextBlock(type="text", text=f"⚠️ 删除无效：在 '{table_name}' 中未找到匹配 {conditions} 的记录。")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 删除出错: {e}")])

    def save_project(self, name: str, progress: str) -> ToolResponse:
        """[存/改] 更新项目进度。"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE agent_name=? AND name=?", (self.agent_name, name))
        row = cursor.fetchone()
        if row:
            self._execute_with_retry("UPDATE projects SET progress=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                                     (progress, row['id']))
        else:
            self._execute_with_retry("INSERT INTO projects (agent_name, name, progress) VALUES (?, ?, ?)",
                                     (self.agent_name, name, progress))
        return ToolResponse(content=[TextBlock(type="text", text=f"✅ 项目 '{name}' 进度已更新")])

    # =================================================
    # 🎬 场景管理工具 (Scene Manager) - 对应 ConceptAgent
    # 命名规范: save_scene / get_scene / del_scene
    # =================================================

    def save_scene(self, project: str, scene: str,
                   world_prompt: str = None,
                   elements: str = None,
                   mood: str = None,
                   color_tone: str = None,
                   lighting_mood: str = None) -> ToolResponse:
        """
        [存/改] 登记或更新场景的视觉设定。

        Args:
            project (str): 项目名称 (如 'MyMovie').
            scene (str): 场次编号 (如 'Scene_01').
            world_prompt (str): 世界观描述 (宏观设定).
            elements (str): 场景内的关键物体/元素列表.
            mood (str): 整体情绪/氛围.
            color_tone (str): [关键] 画面色调 (e.g., 'Cyberpunk Neon', 'Desaturated Sepia').
            lighting_mood (str): [关键] 光影基调 (e.g., 'High Key', 'Film Noir', 'Natural').

        Returns:
            ToolResponse: 操作结果消息.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT id FROM scenes WHERE project=? AND scene=?', (project, scene))
            row = cursor.fetchone()

            if row:
                # 更新逻辑
                fields = []
                params = []
                if world_prompt: fields.append("world_prompt=?"); params.append(world_prompt)
                if elements: fields.append("elements=?"); params.append(elements)
                if mood: fields.append("mood=?"); params.append(mood)
                if color_tone: fields.append("color_tone=?"); params.append(color_tone)
                if lighting_mood: fields.append("lighting_mood=?"); params.append(lighting_mood)

                if not fields:
                    return ToolResponse(content=[TextBlock(type="text", text="⚠️ 场景表未发生变更 (未传入有效字段)")])

                sql = f"UPDATE scenes SET {', '.join(fields)} WHERE id=?"
                params.append(row[0])
                self._execute_with_retry(sql, tuple(params))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 场景已更新: {scene}")])
            else:
                # 创建逻辑
                sql = '''INSERT INTO scenes (project, scene, world_prompt, elements, mood, color_tone, lighting_mood)
                         VALUES (?, ?, ?, ?, ?, ?, ?)'''
                self._execute_with_retry(sql, (project, scene, world_prompt, elements, mood, color_tone, lighting_mood))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 新场景已创建: {scene}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def get_scene(self, project: str, scene: str) -> ToolResponse:
        """
        [查] 获取场景详情。

        Args:
            project (str): 项目名称.
            scene (str): 场次编号.

        Returns:
            ToolResponse: 包含场景所有视觉参数的文本块.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM scenes WHERE project=? AND scene=?', (project, scene))
            row = cursor.fetchone()
            if row:
                data = dict(row)
                info = (
                    f"🎬 [Scene: {data['scene']}]\n"
                    f"🌍 World: {data['world_prompt'] or 'N/A'}\n"
                    f"🧩 Elements: {data['elements'] or 'N/A'}\n"
                    f"🎨 Mood: {data['mood'] or 'N/A'}\n"
                    f"🌈 Color Tone: {data['color_tone'] or 'Not defined'}\n"
                    f"💡 Lighting Mood: {data['lighting_mood'] or 'Not defined'}"
                )
                return ToolResponse(content=[TextBlock(type="text", text=info)])
            else:
                return ToolResponse(content=[TextBlock(type="text", text=f"📭 未找到场景 '{scene}' 的设定信息。")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def del_scene(self, project: str, scene: str) -> ToolResponse:
        """[删] 删除某个场景的全部设定。"""
        try:
            sql = "DELETE FROM scenes WHERE project=? AND scene=?"
            cursor = self._execute_with_retry(sql, (project, scene))
            if cursor.rowcount > 0:
                return ToolResponse(content=[TextBlock(type="text", text=f"🗑️ 场景 '{scene}' 已删除。")])
            else:
                return ToolResponse(content=[TextBlock(type="text", text=f"⚠️ 未找到场景，删除无效。")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 删除场景失败: {e}")])

    # =================================================
    # 🎥 镜头管理工具 (Shot Manager) - 对应 StoryboardAgent
    # 命名规范: save_shot / get_shot / del_shot
    # =================================================
    def save_shot(self, project: str, scene: str, shot: str, version: int = 1,
                  prompt_file_path: str = None,
                  image_path: str = None,
                  status: str = None,
                  remarks: str = None,
                  shot_size: str = None,
                  camera_angle: str = None,
                  camera_movement: str = None,
                  lighting: str = None) -> ToolResponse:
        """
        [分镜表登记/更新] 记录镜头的 Prompt 文件位置、图片路径以及详细的镜头语言参数。

        Args:
            project (str): 项目名称.
            scene (str): 场次编号.
            shot (str): 镜头编号 (如 'Shot_05').
            version (int): 版本号 (默认 1).
            prompt_file_path (str): [规划阶段] Prompt JSON 文件的本地路径.
            image_path (str): [完成阶段] Bot 下载的图片本地路径.
            status (str): 状态流转 ('planning' -> 'generating' -> 'done' -> 'audited'/'rejected').
            remarks (str): 监制反馈或备注.
            shot_size (str): 景别 (e.g., 'Extreme Wide Shot', 'Medium Shot', 'Close-up').
            camera_angle (str): 拍摄角度 (e.g., 'Eye-level', 'Low angle', 'Bird\'s eye').
            camera_movement (str): 运镜方式 (e.g., 'Static', 'Pan Left', 'Dolly In').
            lighting (str): 光照设定 (e.g., 'Natural Soft', 'Rim Light', 'Hard Shadow').

        Returns:
            ToolResponse: 操作结果.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                           SELECT id
                           FROM production_assets
                           WHERE project = ?
                             AND scene = ?
                             AND shot = ?
                             AND version = ?
                           ''', (project, scene, shot, version))
            row = cursor.fetchone()

            if row:
                # === 更新现有记录 (Backfill/Update) ===
                shot_id = row[0]
                fields = []
                params = []

                if prompt_file_path: fields.append("prompt_path=?"); params.append(prompt_file_path)
                if image_path: fields.append("image_path=?"); params.append(image_path)
                if status: fields.append("status=?"); params.append(status)
                if remarks: fields.append("audit_feedback=?"); params.append(remarks)

                # 更新镜头语言
                if shot_size: fields.append("shot_size=?"); params.append(shot_size)
                if camera_angle: fields.append("camera_angle=?"); params.append(camera_angle)
                if camera_movement: fields.append("camera_movement=?"); params.append(camera_movement)
                if lighting: fields.append("lighting=?"); params.append(lighting)

                if not fields:
                    return ToolResponse(content=[TextBlock(type="text", text="⚠️ 无字段变更。")])

                fields.append("updated_at=CURRENT_TIMESTAMP")
                sql = f"UPDATE production_assets SET {', '.join(fields)} WHERE id=?"
                params.append(shot_id)
                self._execute_with_retry(sql, tuple(params))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 分镜表已更新: {shot} v{version}")])

            else:
                # === 创建新记录 (Register/Plan) ===
                sql = '''
                      INSERT INTO production_assets (project, scene, shot, version, prompt_path, image_path, status, \
                                                     audit_feedback, \
                                                     shot_size, camera_angle, camera_movement, lighting) \
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                      '''
                final_status = status or 'planning'
                params = (
                    project, scene, shot, version, prompt_file_path, image_path, final_status, remarks,
                    shot_size, camera_angle, camera_movement, lighting
                )
                self._execute_with_retry(sql, params)
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 分镜条目已规划: {shot} v{version}")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def get_shot(self, project: str, scene: str, shot: str, version: int = None) -> ToolResponse:
        """
        [查] 获取分镜详情。如果不指定版本，默认返回最新的一个版本。

        Args:
            project (str): 项目名称.
            scene (str): 场次编号.
            shot (str): 镜头编号.
            version (int, optional): 指定版本号.

        Returns:
            ToolResponse: 包含路径、状态和镜头参数的 JSON 格式数据.
        """
        try:
            cursor = self.conn.cursor()
            if version:
                sql = "SELECT * FROM production_assets WHERE project=? AND scene=? AND shot=? AND version=?"
                params = (project, scene, shot, version)
            else:
                sql = "SELECT * FROM production_assets WHERE project=? AND scene=? AND shot=? ORDER BY version DESC LIMIT 1"
                params = (project, scene, shot)

            rows = cursor.execute(sql, params).fetchall()

            result_data = []
            for row in rows:
                item = dict(row)
                # 将镜头参数聚合，方便阅读
                item['cinematography'] = {
                    "size": item.get('shot_size') or "N/A",
                    "angle": item.get('camera_angle') or "N/A",
                    "movement": item.get('camera_movement') or "N/A",
                    "lighting": item.get('lighting') or "N/A"
                }
                result_data.append(item)

            if result_data:
                return ToolResponse(
                    content=[TextBlock(type="text", text=json.dumps(result_data, indent=2, ensure_ascii=False))])
            else:
                return ToolResponse(content=[TextBlock(type="text", text="📭 未找到该镜头记录。")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def del_shot(self, project: str, scene: str, shot: str, version: int = None) -> ToolResponse:
        """[删] 删除镜头记录。如果不传 version，删除该镜头所有版本！"""
        try:
            if version:
                sql = "DELETE FROM production_assets WHERE project=? AND scene=? AND shot=? AND version=?"
                params = (project, scene, shot, version)
            else:
                sql = "DELETE FROM production_assets WHERE project=? AND scene=? AND shot=?"
                params = (project, scene, shot)

            cursor = self._execute_with_retry(sql, params)
            return ToolResponse(content=[TextBlock(type="text", text=f"🗑️ 已删除 {cursor.rowcount} 条镜头记录。")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 删除镜头失败: {e}")])

    # =================================================
    # 💃 Design Tools (角色管理 - 本地优先版)
    # =================================================

    def save_design_asset(self, project: str, category: str, name: str,
                          prompt_file_path: str = None,
                          image_path: str = None,
                          attributes: str = None,  # 存性格、材质等
                          status: str = None,
                          remarks: str = None) -> ToolResponse:
        """
        [通用登记] 保存视觉资产 (角色、道具、场景图等)。
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT id FROM design_assets WHERE project=? AND category=? AND name=?',
                           (project, category, name))
            row = cursor.fetchone()

            if row:
                fields = []
                params = []
                if prompt_file_path: fields.append("prompt_path=?"); params.append(prompt_file_path)
                if image_path: fields.append("image_path=?"); params.append(image_path)
                if attributes: fields.append("attributes=?"); params.append(attributes)
                if status: fields.append("status=?"); params.append(status)
                if remarks: fields.append("remarks=?"); params.append(remarks)

                if not fields: return ToolResponse(content=[TextBlock(type="text", text="⚠️ 无变更。")])

                sql = f"UPDATE design_assets SET {', '.join(fields)} WHERE id=?"
                params.append(row[0])
                self._execute_with_retry(sql, tuple(params))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 资产已更新: {name} ({category})")])
            else:
                sql = '''INSERT INTO design_assets (project, category, name, prompt_path, image_path, attributes, \
                                                    status, remarks)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)'''
                final_status = status or 'planning'
                self._execute_with_retry(sql, (project, category, name, prompt_file_path, image_path, attributes,
                                               final_status, remarks))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 新资产已登记: {name} ({category})")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def get_design_asset(self, project: str, category: str, name: str) -> ToolResponse:
        """[查] 获取资产详情"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM design_assets WHERE project=? AND category=? AND name=?',
                           (project, category, name))
            row = cursor.fetchone()
            if row:
                return ToolResponse(
                    content=[TextBlock(type="text", text=json.dumps(dict(row), indent=2, ensure_ascii=False))])
            else:
                return ToolResponse(content=[TextBlock(type="text", text=f"📭 未找到 {category}: '{name}'")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    # =================================================
    # 🛠️ 系统配置工具 (System & Config) - 模版与通用
    # =================================================

    def get_prompt_template(self, model_key: str) -> ToolResponse:
        """
        根据模型关键词获取 Prompt 模版。
        Args:
            model_key: 模型的简称，例如 'mj', 'sd', 'flux'。
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT template FROM prompt_templates WHERE model_key = ?", (model_key.lower(),))
            row = cursor.fetchone()

            if row:
                return ToolResponse(content=[TextBlock(type="text", text=row[0])])
            else:
                cursor.execute("SELECT model_key FROM prompt_templates")
                keys = [r[0] for r in cursor.fetchall()]
                return ToolResponse(
                    content=[TextBlock(type="text", text=f"❌ 未找到 '{model_key}' 的模版。可用模版: {', '.join(keys)}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 查询模版出错: {e}")])

    def execute_sql_query(self, table_name: str, filter_conditions: dict = None) -> ToolResponse:
        """
        [通用工具] 根据条件查询数据库中的特定表格。

        Args:
            table_name: 目标表名 (如 'tasks', 'calendars', 'patterns')
            filter_conditions: 筛选条件字典。例如 {"status": "todo"} 或 {"id": 1}。留空则查询所有。
        """
        try:
            # 1. 安全检查：防止查询不存在的表
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table_name,))
            if not cursor.fetchone():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 错误：表 '{table_name}' 不存在。")])

            # 2. 构建 SQL 语句
            sql = f"SELECT * FROM {table_name}"
            params = []

            if filter_conditions:
                clauses = []
                for k, v in filter_conditions.items():
                    # 简单的等于查询，如果需要更复杂(如包含、大于)，可以在这里扩展
                    clauses.append(f"{k} = ?")
                    params.append(v)

                if clauses:
                    sql += " WHERE " + " AND ".join(clauses)

            # 限制条数防止 Token 爆炸
            sql += " ORDER BY id DESC LIMIT 20"

            # 3. 执行查询
            # 使用 row_factory 确保结果是字典形式，方便阅读
            self.conn.row_factory = sqlite3.Row
            cur = self.conn.cursor()  # 重新获取 cursor 以应用 row_factory
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

            # 4. 格式化结果
            if not rows:
                return ToolResponse(content=[TextBlock(type="text", text=f"📭 表 '{table_name}' 中未找到匹配记录。")])

            # 转为 JSON 字符串
            result_list = [dict(row) for row in rows]
            json_result = json.dumps(result_list, ensure_ascii=False, indent=2)

            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 查询结果 ({len(rows)}条):\n{json_result}")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 查询异常: {str(e)}")])

    def promote_pattern_to_memory(self, pattern_text: str) -> ToolResponse:
        """
        [Fix] 补回：将重要规律标记为'需写入长期记忆'。
        """
        return ToolResponse(content=[TextBlock(type="text",
                                               text=f"🚀 建议操作：请立即调用 `record_to_memory` 工具(如有)或记录在 Memento 中，内容：\n{pattern_text}")])

    def save_memento(self, content: str) -> ToolResponse:
        self._execute_with_retry("INSERT INTO mementos (agent_name, content) VALUES (?, ?)", (self.agent_name, content))
        return ToolResponse(content=[TextBlock(type="text", text="✅ Memento Saved")])

    def add_pattern(self, observation: str) -> ToolResponse:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, hit_count FROM patterns WHERE agent_name=? AND content=?",
                       (self.agent_name, observation))
        row = cursor.fetchone()
        if row:
            self._execute_with_retry("UPDATE patterns SET hit_count=hit_count+1 WHERE id=?", (row['id'],))
        else:
            self._execute_with_retry("INSERT INTO patterns (agent_name, content) VALUES (?, ?)",
                                     (self.agent_name, observation))
        return ToolResponse(content=[TextBlock(type="text", text="✅ Pattern Recorded")])

    def get_dashboard(self, role: str = 'default', project: str = None, scene: str = None) -> ToolResponse:
        """
        [仪表盘] 获取工作台状态。支持三种视图模式，请根据当前工作阶段选择参数。

        Args:
            role (str): 角色视图 ('prompter'/'concept'/'storyboard' 或 'scheduler'/'default').
            project (str, optional): 项目名称。如果只传项目，将显示该项目的【场次列表】。
            scene (str, optional): 场次名称。如果同时传入项目和场次，将进入【沉浸式工作台】，显示该场次的所有设定、镜头和素材。
        """
        try:
            cursor = self.conn.cursor()
            lines = []

            # =========================================================
            # 🎨 模式 A: 创意角色 (美术/分镜)
            # =========================================================
            if role in ['prompter', 'concept', 'storyboard']:

                # --- 子模式 1: 沉浸式场次视图 (Project + Scene) ---
                # 当 Agent 明确要处理某一场戏时，显示极详尽的局部信息
                if project and scene:
                    lines.append(f"🎬 === 沉浸式工作台: {project} / {scene} ===")

                    # 1. 读取场景设定 (Scenes 表)
                    cursor.execute(
                        "SELECT world_prompt, elements, characters, concept_url, status FROM scenes WHERE project=? AND scene=?",
                        (project, scene))
                    row = cursor.fetchone()
                    if row:
                        status_icon = "🟢" if row['status'] == 'confirmed' else "📝"
                        lines.append(f"\n[场景设定 {status_icon}]")
                        lines.append(f"- 状态: {row['status']}")
                        lines.append(f"- 核心元素: {row['elements'] or '(未设定)'}")
                        lines.append(f"- 在场角色: {row['characters'] or '(未设定)'}")
                        lines.append(f"- 世界观Prompt: {row['world_prompt'][:100]}..." if row[
                            'world_prompt'] else "- 世界观Prompt: (空)")
                        if row['concept_url']: lines.append(f"- 概念图: 已上传 OSS")
                    else:
                        lines.append(f"\n[场景设定] ⚠️ 尚未初始化 (请调用 save_scene 创建)")

                    # 2. 读取镜头列表 (Production Assets 表)
                    # 只显示当前场的镜头，不看别的
                    lines.append(f"\n[镜头列表 Shot List]")
                    cursor.execute('''
                                   SELECT shot, version, status
                                   FROM production_assets
                                   WHERE project = ?
                                     AND scene = ?
                                   ORDER BY shot ASC, version DESC
                                   ''', (project, scene))
                    rows = cursor.fetchall()
                    if rows:
                        # 简单的去重逻辑，只显示每个镜头的最新版
                        shots_seen = set()
                        for r in rows:
                            if r['shot'] not in shots_seen:
                                icon = "✅" if r['status'] == 'audited' else "🎨"
                                lines.append(f"- {r['shot']} (v{r['version']}) {icon} {r['status']}")
                                shots_seen.add(r['shot'])
                    else:
                        lines.append("(暂无镜头资产)")

                    # 3. 读取该场的参考图
                    lines.append(f"\n[参考素材 Image Refs]")
                    cursor.execute("SELECT usage_type, remark FROM image_references WHERE project=? AND scene=?",
                                   (project, scene))
                    rows = cursor.fetchall()
                    if rows:
                        for r in rows:
                            lines.append(f"- [{r['usage_type']}] {r['remark']}")
                    else:
                        lines.append("(无)")

                # --- 子模式 2: 项目视图 (Project Only) ---
                # 当 Agent 想知道项目里有哪些场需要做时
                elif project:
                    lines.append(f"🚀 === 项目概览: {project} ===")

                    # 读取该项目下的所有场
                    cursor.execute("SELECT scene, status, updated_at FROM scenes WHERE project=? ORDER BY scene ASC",
                                   (project,))
                    rows = cursor.fetchall()
                    lines.append(f"\n[场次列表 Scene List]")
                    if rows:
                        for r in rows:
                            lines.append(f"- {r['scene']} ({r['status']}) - Last Update: {r['updated_at'][:16]}")
                    else:
                        lines.append("(该项目暂无场次，请调用 save_scene 初始化)")

                # --- 子模式 3: 全局概览 (无参数) ---
                # Agent 刚醒来，看一眼有哪些待办，有哪些项目
                else:
                    lines.append(f"👋 === 创意总监概览 (Global View) ===")

                    # 待办任务
                    lines.append(f"\n[待办任务 Tasks]")
                    cursor.execute(
                        "SELECT id, content, priority FROM tasks WHERE agent_name=? AND status='todo' ORDER BY priority ASC LIMIT 5",
                        (self.agent_name,))
                    rows = cursor.fetchall()
                    for r in rows:
                        prio = "🔥" if r['priority'] < 2 else ""
                        lines.append(f"- {prio}[ID:{r['id']}] {r['content']}")
                    if not rows: lines.append("(无待办)")

                    # 活跃项目列表
                    lines.append(f"\n[活跃项目 Projects]")
                    cursor.execute("SELECT DISTINCT project FROM scenes LIMIT 10")
                    rows = cursor.fetchall()
                    if rows:
                        lines.append(
                            "检测到以下项目包含场景数据，请使用 get_dashboard(role='prompter', project='...') 查看详情：")
                        for r in rows:
                            lines.append(f"- {r['project']}")
                    else:
                        lines.append("(暂无活跃项目)")

            # =========================================================
            # 📅 模式 B: 行政角色 (Scheduler/Default) - 保持全局视角
            # =========================================================
            else:
                lines.append(f"📅 === 行政总览 (Scheduler View) ===")

                # 待办任务
                lines.append(f"\n[Tasks]")
                cursor.execute(
                    "SELECT id, content, lark_id, due_date FROM tasks WHERE agent_name=? AND status='todo' ORDER BY priority ASC",
                    (self.agent_name,))
                rows = cursor.fetchall()
                for r in rows:
                    lark_mark = f"[Lark:{r['lark_id'][-4:]}]" if r['lark_id'] else ""
                    lines.append(f"- [ ] ID:{r['id']} {lark_mark} {r['content']} (Due: {r['due_date']})")

                # 日程
                lines.append(f"\n[Calendars]")
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute(
                    "SELECT content, start_time FROM calendars WHERE agent_name=? AND end_time > ? ORDER BY start_time ASC LIMIT 5",
                    (self.agent_name, now_str))
                for r in rows:
                    lines.append(f"- 🕒 {r['start_time']} | {r['content']}")

                # 项目进度
                lines.append(f"\n[Projects]")
                cursor.execute("SELECT name, progress FROM projects WHERE agent_name=?", (self.agent_name,))
                for r in rows:
                    lines.append(f"- 【{r['name']}】: {r['progress']}")

            # 公共备忘
            lines.append(f"\n🧠 [Mementos]")
            cursor.execute("SELECT content FROM mementos WHERE agent_name=? ORDER BY id DESC LIMIT 2",
                           (self.agent_name,))
            rows = cursor.fetchall()
            if rows:
                for r in rows: lines.append(f"- {r['content']}")

            return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 看板加载失败: {e}")])

    def update_task_status(self, task_id: int, status: str) -> ToolResponse:
        self._execute_with_retry("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
        return ToolResponse(content=[TextBlock(type="text", text="✅ Status Updated")])

    def close(self):
        if self.conn:
            self.conn.close()