import sqlite3
import os
import time
import datetime
import json
import asyncio
from typing import List, Dict, Optional

from agentscope.tool import ToolResponse
from agentscope.message import TextBlock
from src.core.file_manager import FileManager


class AgentNotebook:

    # 公共/私有表集合，便于路由到对应数据库
    SHARED_TABLES = {
        "tasks", "calendars", "projects", "patterns", "resources",
        "production_assets", "scenes", "design_assets"
    }
    PRIVATE_TABLES = {"mementos", "patterns_private"}

    def __init__(self, agent_name: str, shared_db_name: str = "agent_shared.db", private_db_name: str = None,
                 long_term_memory: Optional[object] = None):
        self.agent_name = agent_name

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.data_dir = os.path.join(base_dir, "data")
        shared_dir = os.path.join(self.data_dir, "shared")
        private_dir = os.path.join(self.data_dir, "private", agent_name)
        os.makedirs(shared_dir, exist_ok=True)
        os.makedirs(private_dir, exist_ok=True)

        self.shared_db_path = os.path.join(shared_dir, shared_db_name)
        private_db_name = private_db_name or f"{agent_name}_notes.db"
        self.private_db_path = os.path.join(private_dir, private_db_name)

        self.file_manager = FileManager()
        self.long_term_memory = long_term_memory

        self.shared_conn = sqlite3.connect(self.shared_db_path, check_same_thread=False)
        self.shared_conn.row_factory = sqlite3.Row

        self.private_conn = sqlite3.connect(self.private_db_path, check_same_thread=False)
        self.private_conn.row_factory = sqlite3.Row

        self._init_shared_tables()
        self._init_private_tables()

        # 简单去重缓存：避免短时间内重复查询同一场景
        self._last_scene_query = {
            "key": None,
            "ts": 0.0,
            "response": None
        }

    def _init_shared_tables(self):
        cursor = self.shared_conn.cursor()

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS tasks
                       (
                           id         INTEGER PRIMARY KEY AUTOINCREMENT,
                           agent_name TEXT NOT NULL,
                           lark_id    TEXT UNIQUE,
                           content    TEXT NOT NULL,
                           status     TEXT      DEFAULT 'todo',
                           due_date   TEXT,
                           priority   INTEGER   DEFAULT 2,
                           created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           updated_at TIMESTAMP
                       )
                       ''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS calendars
                       (
                           id            INTEGER PRIMARY KEY AUTOINCREMENT,
                           agent_name    TEXT NOT NULL,
                           lark_event_id TEXT UNIQUE,
                           content       TEXT NOT NULL,
                           start_time    TEXT NOT NULL,
                           end_time      TEXT NOT NULL,
                           created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                       )
                       ''')

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

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS production_assets
                       (
                           id              INTEGER PRIMARY KEY AUTOINCREMENT,
                           project         TEXT,
                           scene           TEXT,
                           shot            TEXT,
                           version         INTEGER,
                           prompt_path     TEXT,
                           image_path      TEXT,
                           status          TEXT,
                           audit_feedback  TEXT,
                           shot_size       TEXT,
                           camera_angle    TEXT,
                           camera_movement TEXT,
                           lighting        TEXT,
                           updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           UNIQUE (project, scene, shot, version)
                       );
                       ''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS scenes
                       (
                           id            INTEGER PRIMARY KEY AUTOINCREMENT,
                           project       TEXT,
                           scene         TEXT,
                           world_prompt  TEXT,
                           elements      TEXT,
                           mood          TEXT,
                           color_tone    TEXT,
                           lighting_mood TEXT,
                           characters    TEXT,
                           concept_url   TEXT,
                           status        TEXT,
                           created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           UNIQUE (project, scene)
                       );
                       ''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS design_assets
                       (
                           id            INTEGER PRIMARY KEY AUTOINCREMENT,
                           project       TEXT NOT NULL,
                           name          TEXT NOT NULL,
                           category      TEXT NOT NULL,
                           prompt_path   TEXT,
                           image_path    TEXT,
                           attributes    TEXT,
                           oss_url_cache TEXT,
                           status        TEXT,
                           remarks       TEXT,
                           created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           UNIQUE (project, name, category)
                       );
                       ''')

        self.shared_conn.commit()

    def _init_private_tables(self):
        cursor = self.private_conn.cursor()

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS mementos
                       (
                           id         INTEGER PRIMARY KEY AUTOINCREMENT,
                           agent_name TEXT NOT NULL,
                           content    TEXT NOT NULL,
                           created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                       )
                       ''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS patterns_private
                       (
                           id           INTEGER PRIMARY KEY AUTOINCREMENT,
                           agent_name   TEXT NOT NULL,
                           content      TEXT NOT NULL UNIQUE,
                           hit_count    INTEGER   DEFAULT 1,
                           is_promoted  BOOLEAN   DEFAULT 0,
                           last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                       )
                       ''')

        self.private_conn.commit()

    def _execute_with_retry(self, conn, sql: str, params: tuple = (), max_retries=5):
        for i in range(max_retries):
            try:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                conn.commit()
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

    def _get_conn_and_cursor(self, table_name: str):
        if table_name in self.SHARED_TABLES:
            return self.shared_conn, self.shared_conn.cursor()
        if table_name in self.PRIVATE_TABLES:
            return self.private_conn, self.private_conn.cursor()
        return None, None

    def get_schema_prompt(self, scope: str = "all") -> str:
        def _collect(conn, title):
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence';")
            tables = cursor.fetchall()
            lines = [f"## {title}", "可用表："]
            for table in tables:
                t_name = table[0]
                cursor.execute(f"PRAGMA table_info({t_name})")
                columns = [col[1] for col in cursor.fetchall()]
                lines.append(f"- {t_name}: {columns}")
            return lines

        prompt_lines = ["\n## 📂 数据库结构 (用于 query_database 工具)"]
        if scope in ("shared", "all"):
            prompt_lines.extend(_collect(self.shared_conn, "Shared DB"))
        if scope in ("private", "all"):
            prompt_lines.extend(_collect(self.private_conn, "Private DB"))

        return "\n".join(prompt_lines)

    def save_schedule(self, table_name: str, data: dict) -> ToolResponse:
        try:
            conn, cursor = self._get_conn_and_cursor(table_name)
            if not cursor:
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 错误：表 '{table_name}' 不存在。")])

            if table_name == 'tasks' and 'updated_at' not in data:
                data['updated_at'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            columns = list(data.keys())
            placeholders = ["?"] * len(columns)
            values = list(data.values())

            sql = f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"

            self._execute_with_retry(conn, sql, tuple(values))

            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 数据已保存至 '{table_name}'")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 保存失败: {e} (请检查字段名是否正确)")])

    def delete_schedule(self, table_name: str, conditions: dict) -> ToolResponse:
        if not conditions:
            return ToolResponse(
                content=[TextBlock(type="text", text="❌ 拒绝操作：必须提供删除条件 (conditions)，防止误删全表。")])

        try:
            conn, cursor = self._get_conn_and_cursor(table_name)
            if not cursor:
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 表 '{table_name}' 不存在")])

            clauses = []
            params = []
            for k, v in conditions.items():
                clauses.append(f"{k} = ?")
                params.append(v)

            where_sql = " AND ".join(clauses)
            sql = f"DELETE FROM {table_name} WHERE {where_sql}"

            cursor = self._execute_with_retry(conn, sql, tuple(params))

            if cursor.rowcount > 0:
                return ToolResponse(content=[
                    TextBlock(type="text", text=f"✅ 删除成功：已从 '{table_name}' 移除 {cursor.rowcount} 条记录。")])
            else:
                return ToolResponse(content=[
                    TextBlock(type="text", text=f"⚠️ 删除无效：在 '{table_name}' 中未找到匹配 {conditions} 的记录。")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 删除出错: {e}")])

    def save_project(self, name: str, progress: str) -> ToolResponse:
        cursor = self.shared_conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE agent_name=? AND name=?", (self.agent_name, name))
        row = cursor.fetchone()
        if row:
            self._execute_with_retry(self.shared_conn,
                                     "UPDATE projects SET progress=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                                     (progress, row['id']))
        else:
            self._execute_with_retry(self.shared_conn,
                                     "INSERT INTO projects (agent_name, name, progress) VALUES (?, ?, ?)",
                                     (self.agent_name, name, progress))
        return ToolResponse(content=[TextBlock(type="text", text=f"✅ 项目 '{name}' 进度已更新")])

    def save_scene(self, project: str, scene: str,
                   world_prompt: str = None,
                   elements: str = None,
                   mood: str = None,
                   color_tone: str = None,
                   lighting_mood: str = None,
                   characters: str = None,
                   concept_url: str = None,
                   status: str = None) -> ToolResponse:
        try:
            cursor = self.shared_conn.cursor()
            cursor.execute('SELECT id FROM scenes WHERE project=? AND scene=?', (project, scene))
            row = cursor.fetchone()

            if row:
                fields = []
                params = []
                if world_prompt: fields.append("world_prompt=?"); params.append(world_prompt)
                if elements: fields.append("elements=?"); params.append(elements)
                if mood: fields.append("mood=?"); params.append(mood)
                if color_tone: fields.append("color_tone=?"); params.append(color_tone)
                if lighting_mood: fields.append("lighting_mood=?"); params.append(lighting_mood)
                if characters: fields.append("characters=?"); params.append(characters)
                if concept_url: fields.append("concept_url=?"); params.append(concept_url)
                if status: fields.append("status=?"); params.append(status)

                if not fields:
                    return ToolResponse(content=[TextBlock(type="text", text="⚠️ 场景表未发生变更 (未传入有效字段)")])

                fields.append("updated_at=CURRENT_TIMESTAMP")
                sql = f"UPDATE scenes SET {', '.join(fields)} WHERE id=?"
                params.append(row[0])
                self._execute_with_retry(self.shared_conn, sql, tuple(params))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 场景已更新: {scene}")])
            else:
                sql = '''INSERT INTO scenes (project, scene, world_prompt, elements, mood, color_tone, lighting_mood, characters, concept_url, status)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
                self._execute_with_retry(self.shared_conn, sql,
                                         (project, scene, world_prompt, elements, mood, color_tone, lighting_mood,
                                          characters, concept_url, status))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 新场景已创建: {scene}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def get_scene(self, project: str, scene: str) -> ToolResponse:
        try:
            cache_key = f"{project}::{scene}"
            now_ts = time.time()
            if self._last_scene_query["key"] == cache_key and (now_ts - self._last_scene_query["ts"]) < 5:
                cached = self._last_scene_query["response"]
                if cached:
                    return ToolResponse(content=[TextBlock(type="text", text=f"⚠️ 已查询该场景（缓存结果）：\n{cached}")])

            cursor = self.shared_conn.cursor()
            cursor.execute('SELECT * FROM scenes WHERE project=? AND scene=?', (project, scene))
            row = cursor.fetchone()
            if row:
                data = dict(row)
                info = (
                    f"🎬 [Scene: {data['scene']}]\n"
                    f"🌍 World: {data.get('world_prompt') or 'N/A'}\n"
                    f"🧩 Elements: {data.get('elements') or 'N/A'}\n"
                    f"🎨 Mood: {data.get('mood') or 'N/A'}\n"
                    f"🌈 Color Tone: {data.get('color_tone') or 'Not defined'}\n"
                    f"💡 Lighting Mood: {data.get('lighting_mood') or 'Not defined'}\n"
                    f"🧑 Characters: {data.get('characters') or 'Not defined'}\n"
                    f"🖼️ Concept: {data.get('concept_url') or 'Not uploaded'}\n"
                    f"📌 Status: {data.get('status') or 'unknown'}"
                )
                self._last_scene_query.update({"key": cache_key, "ts": now_ts, "response": info})
                return ToolResponse(content=[TextBlock(type="text", text=info)])
            else:
                info = f"📭 未找到场景 '{scene}' 的设定信息。"
                self._last_scene_query.update({"key": cache_key, "ts": now_ts, "response": info})
                return ToolResponse(content=[TextBlock(type="text", text=info)])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def del_scene(self, project: str, scene: str) -> ToolResponse:
        try:
            sql = "DELETE FROM scenes WHERE project=? AND scene=?"
            cursor = self._execute_with_retry(self.shared_conn, sql, (project, scene))
            if cursor.rowcount > 0:
                return ToolResponse(content=[TextBlock(type="text", text=f"🗑️ 场景 '{scene}' 已删除。")])
            else:
                return ToolResponse(content=[TextBlock(type="text", text="⚠️ 未找到场景，删除无效。")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 删除场景失败: {e}")])

    def save_shot(self, project: str, scene: str, shot: str, version: int = 1,
                  prompt_file_path: str = None,
                  image_path: str = None,
                  status: str = None,
                  remarks: str = None,
                  shot_size: str = None,
                  camera_angle: str = None,
                  camera_movement: str = None,
                  lighting: str = None) -> ToolResponse:
        try:
            cursor = self.shared_conn.cursor()
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
                shot_id = row[0]
                fields = []
                params = []

                if prompt_file_path: fields.append("prompt_path=?"); params.append(prompt_file_path)
                if image_path: fields.append("image_path=?"); params.append(image_path)
                if status: fields.append("status=?"); params.append(status)
                if remarks: fields.append("audit_feedback=?"); params.append(remarks)

                if shot_size: fields.append("shot_size=?"); params.append(shot_size)
                if camera_angle: fields.append("camera_angle=?"); params.append(camera_angle)
                if camera_movement: fields.append("camera_movement=?"); params.append(camera_movement)
                if lighting: fields.append("lighting=?"); params.append(lighting)

                if not fields:
                    return ToolResponse(content=[TextBlock(type="text", text="⚠️ 无字段变更。")])

                fields.append("updated_at=CURRENT_TIMESTAMP")
                sql = f"UPDATE production_assets SET {', '.join(fields)} WHERE id=?"
                params.append(shot_id)
                self._execute_with_retry(self.shared_conn, sql, tuple(params))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 分镜表已更新: {shot} v{version}")])

            else:
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
                self._execute_with_retry(self.shared_conn, sql, params)
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 分镜条目已规划: {shot} v{version}")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def get_shot(self, project: str, scene: str, shot: str, version: int = None) -> ToolResponse:
        try:
            cursor = self.shared_conn.cursor()
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
                item['cinematography'] = {
                    "size": item.get('shot_size') or "N/A",
                    "angle": item.get('camera_angle') or "N/A",
                    "movement": item.get('camera_movement') or "N/A",
                    "lighting": item.get('lighting') or "N/A"
                }
                result_data.append(item)

            if result_data:
                return ToolResponse(content=[TextBlock(type="text", text=json.dumps(result_data, indent=2, ensure_ascii=False))])
            else:
                return ToolResponse(content=[TextBlock(type="text", text="📭 未找到该镜头记录。")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def del_shot(self, project: str, scene: str, shot: str, version: int = None) -> ToolResponse:
        try:
            if version:
                sql = "DELETE FROM production_assets WHERE project=? AND scene=? AND shot=? AND version=?"
                params = (project, scene, shot, version)
            else:
                sql = "DELETE FROM production_assets WHERE project=? AND scene=? AND shot=?"
                params = (project, scene, shot)

            cursor = self._execute_with_retry(self.shared_conn, sql, params)
            return ToolResponse(content=[TextBlock(type="text", text=f"🗑️ 已删除 {cursor.rowcount} 条镜头记录。")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 删除镜头失败: {e}")])

    def save_design_asset(self, project: str, category: str, name: str,
                          prompt_file_path: str = None,
                          image_path: str = None,
                          attributes: str = None,
                          status: str = None,
                          remarks: str = None) -> ToolResponse:
        try:
            cursor = self.shared_conn.cursor()
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

                if not fields:
                    return ToolResponse(content=[TextBlock(type="text", text="⚠️ 无变更。")])

                sql = f"UPDATE design_assets SET {', '.join(fields)} WHERE id=?"
                params.append(row[0])
                self._execute_with_retry(self.shared_conn, sql, tuple(params))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 资产已更新: {name} ({category})")])
            else:
                sql = '''INSERT INTO design_assets (project, category, name, prompt_path, image_path, attributes, status, remarks)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)'''
                final_status = status or 'planning'
                params = (project, category, name, prompt_file_path, image_path, attributes, final_status, remarks)
                self._execute_with_retry(self.shared_conn, sql, params)
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 新资产已登记: {name} ({category})")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def save_character(self, project: str, name: str,
                       prompt_file_path: str = None,
                       image_path: str = None,
                       attributes: str = None,
                       status: str = None,
                       remarks: str = None) -> ToolResponse:
        return self.save_design_asset(
            project=project,
            category="character",
            name=name,
            prompt_file_path=prompt_file_path,
            image_path=image_path,
            attributes=attributes,
            status=status,
            remarks=remarks,
        )

    def get_design_asset(self, project: str, category: str, name: str) -> ToolResponse:
        try:
            cursor = self.shared_conn.cursor()
            cursor.execute('SELECT * FROM design_assets WHERE project=? AND category=? AND name=?',
                           (project, category, name))
            row = cursor.fetchone()
            if row:
                return ToolResponse(content=[TextBlock(type="text", text=json.dumps(dict(row), indent=2, ensure_ascii=False))])
            else:
                return ToolResponse(content=[TextBlock(type="text", text=f"📭 未找到 {category}: '{name}'")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def get_character(self, project: str, name: str) -> ToolResponse:
        return self.get_design_asset(project=project, category="character", name=name)

    def execute_sql_query(self, table_name: str, filter_conditions: dict = None) -> ToolResponse:
        try:
            conn, cursor = self._get_conn_and_cursor(table_name)
            if not cursor:
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 错误：表 '{table_name}' 不存在。")])

            sql = f"SELECT * FROM {table_name}"
            params = []

            if filter_conditions:
                clauses = []
                for k, v in filter_conditions.items():
                    clauses.append(f"{k} = ?")
                    params.append(v)
                if clauses:
                    sql += " WHERE " + " AND ".join(clauses)

            sql += " ORDER BY id DESC LIMIT 20"

            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()

            if not rows:
                return ToolResponse(content=[TextBlock(type="text", text=f"📭 表 '{table_name}' 中未找到匹配记录。")])

            result_list = [dict(row) for row in rows]
            json_result = json.dumps(result_list, ensure_ascii=False, indent=2)

            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 查询结果 ({len(rows)} 条):\n{json_result}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 查询异常: {str(e)}")])

    def promote_pattern_to_memory(self, pattern_text: str) -> ToolResponse:
        return ToolResponse(content=[TextBlock(type="text",
                                               text=f"🚀 建议操作：请立即调用 `record_to_memory` 工具(如有)或记录在 Memento 中，内容：\n{pattern_text}")])

    def save_memento(self, content: str) -> ToolResponse:
        self._execute_with_retry(self.private_conn, "INSERT INTO mementos (agent_name, content) VALUES (?, ?)",
                                 (self.agent_name, content))
        return ToolResponse(content=[TextBlock(type="text", text="✅ Memento Saved")])

    def add_pattern(self, observation: str, is_private: bool = False) -> ToolResponse:
        table = "patterns_private" if is_private else "patterns"
        conn, cursor = self._get_conn_and_cursor(table)
        if not cursor:
            return ToolResponse(content=[TextBlock(type="text", text="❌ Pattern 表不存在")])

        cursor.execute(f"SELECT id, hit_count, is_promoted FROM {table} WHERE agent_name=? AND content=?",
                       (self.agent_name, observation))
        row = cursor.fetchone()
        if row:
            new_count = int(row['hit_count']) + 1
            promoted = bool(row['is_promoted'])
            self._execute_with_retry(
                conn,
                f"UPDATE {table} SET hit_count=?, last_updated=CURRENT_TIMESTAMP WHERE id=?",
                (new_count, row['id'])
            )
        else:
            new_count = 1
            promoted = False
            self._execute_with_retry(
                conn,
                f"INSERT INTO {table} (agent_name, content) VALUES (?, ?)",
                (self.agent_name, observation)
            )

        if not promoted and new_count >= 5:
            self._execute_with_retry(
                conn,
                f"UPDATE {table} SET is_promoted=1, last_updated=CURRENT_TIMESTAMP WHERE agent_name=? AND content=?",
                (self.agent_name, observation)
            )
            self._record_to_long_term(observation)
            return ToolResponse(content=[TextBlock(type="text", text="✅ Pattern 已达 5 次，已写入长期记忆")])

        return ToolResponse(content=[TextBlock(type="text", text=f"✅ Pattern Recorded (Count: {new_count})")])

    def set_long_term_memory(self, memory: object):
        self.long_term_memory = memory

    def _record_to_long_term(self, pattern_text: str):
        if not self.long_term_memory:
            return
        try:
            async def _runner():
                await self.long_term_memory.record_to_memory(
                    thinking="Pattern hit count reached threshold",
                    content=[pattern_text]
                )

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_runner())
            except RuntimeError:
                asyncio.run(_runner())
        except Exception as e:
            print(f"❌ [Memory] Failed to record pattern: {e}")

    def get_dashboard(self, role: str = 'default', project: str = None, scene: str = None) -> ToolResponse:
        """仪表盘：创意/行政双视角，读取公库，备忘取私库"""
        try:
            shared = self.shared_conn.cursor()
            private = self.private_conn.cursor()
            lines = []

            if role in ['prompter', 'concept', 'storyboard']:
                if project and scene:
                    lines.append(f"🎬 === 沉浸式工作台: {project} / {scene} ===")

                    shared.execute(
                        "SELECT world_prompt, elements, characters, concept_url, status FROM scenes WHERE project=? AND scene=?",
                        (project, scene))
                    row = shared.fetchone()
                    if row:
                        status_icon = "🟢" if row['status'] == 'confirmed' else "📝"
                        lines.append(f"\n[场景设定 {status_icon}]")
                        lines.append(f"- 状态: {row['status']}")
                        lines.append(f"- 核心元素: {row['elements'] or '(未设定)'}")
                        lines.append(f"- 在场角色: {row['characters'] or '(未设定)'}")
                        lines.append(f"- 世界观Prompt: {row['world_prompt'][:100]}..." if row['world_prompt'] else "- 世界观Prompt: (空)")
                        if row['concept_url']:
                            lines.append("- 概念图: 已上传 OSS")
                    else:
                        lines.append("\n[场景设定] ⚠️ 尚未初始化 (请调用 save_scene 创建)")

                    lines.append("\n[镜头列表 Shot List]")
                    shared.execute('''
                                   SELECT shot, version, status
                                   FROM production_assets
                                   WHERE project = ?
                                     AND scene = ?
                                   ORDER BY shot ASC, version DESC
                                   ''', (project, scene))
                    shot_rows = shared.fetchall()
                    if shot_rows:
                        shots_seen = set()
                        for r in shot_rows:
                            if r['shot'] not in shots_seen:
                                icon = "✅" if r['status'] == 'audited' else "🎨"
                                lines.append(f"- {r['shot']} (v{r['version']}) {icon} {r['status']}")
                                shots_seen.add(r['shot'])
                    else:
                        lines.append("(暂无镜头资产)")

                elif project:
                    lines.append(f"🚀 === 项目概览: {project} ===")
                    shared.execute("SELECT scene, status, updated_at FROM scenes WHERE project=? ORDER BY scene ASC",
                                   (project,))
                    scene_rows = shared.fetchall()
                    lines.append("\n[场次列表 Scene List]")
                    if scene_rows:
                        for r in scene_rows:
                            lines.append(f"- {r['scene']} ({r['status']}) - Last Update: {r['updated_at'][:16]}")
                    else:
                        lines.append("(该项目暂无场次，请调用 save_scene 初始化)")

                else:
                    lines.append("👋 === 创意总监概览 (Global View) ===")

                    lines.append("\n[待办任务 Tasks]")
                    shared.execute(
                        "SELECT id, content, priority FROM tasks WHERE agent_name=? AND status='todo' ORDER BY priority ASC LIMIT 5",
                        (self.agent_name,))
                    task_rows = shared.fetchall()
                    for r in task_rows:
                        prio = "🔥" if r['priority'] < 2 else ""
                        lines.append(f"- {prio}[ID:{r['id']}] {r['content']}")
                    if not task_rows:
                        lines.append("(无待办)")

                    lines.append("\n[活跃项目 Projects]")
                    shared.execute("SELECT DISTINCT project FROM scenes LIMIT 10")
                    project_rows = shared.fetchall()
                    if project_rows:
                        lines.append("检测到以下项目包含场景数据，请使用 get_dashboard(role='prompter', project='...') 查看详情：")
                        for r in project_rows:
                            lines.append(f"- {r['project']}")
                    else:
                        lines.append("(暂无活跃项目)")

            else:
                lines.append("📅 === 行政总览 (Scheduler View) ===")

                lines.append("\n[Tasks]")
                shared.execute(
                    "SELECT id, content, lark_id, due_date FROM tasks WHERE agent_name=? AND status='todo' ORDER BY priority ASC",
                    (self.agent_name,))
                task_rows = shared.fetchall()
                for r in task_rows:
                    lark_mark = f"[Lark:{r['lark_id'][-4:]}]" if r['lark_id'] else ""
                    lines.append(f"- [ ] ID:{r['id']} {lark_mark} {r['content']} (Due: {r['due_date']})")

                lines.append("\n[Calendars]")
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                shared.execute(
                    "SELECT content, start_time FROM calendars WHERE agent_name=? AND end_time > ? ORDER BY start_time ASC LIMIT 5",
                    (self.agent_name, now_str))
                cal_rows = shared.fetchall()
                for r in cal_rows:
                    lines.append(f"- 🕒 {r['start_time']} | {r['content']}")

                lines.append("\n[Projects]")
                shared.execute("SELECT name, progress FROM projects WHERE agent_name=?", (self.agent_name,))
                project_rows = shared.fetchall()
                for r in project_rows:
                    lines.append(f"- 【{r['name']}】: {r['progress']}")

            lines.append("\n🧠 [Mementos]")
            private.execute("SELECT content FROM mementos WHERE agent_name=? ORDER BY id DESC LIMIT 2",
                            (self.agent_name,))
            memo_rows = private.fetchall()
            if memo_rows:
                for r in memo_rows:
                    lines.append(f"- {r['content']}")

            return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 看板加载失败: {e}")])

    def update_task_status(self, task_id: int, status: str) -> ToolResponse:
        self._execute_with_retry(self.shared_conn, "UPDATE tasks SET status=? WHERE id=?", (status, task_id))
        return ToolResponse(content=[TextBlock(type="text", text="✅ Status Updated")])

    def close(self):
        if self.shared_conn:
            self.shared_conn.close()
        if self.private_conn:
            self.private_conn.close()
