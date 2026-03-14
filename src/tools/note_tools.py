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
        "shots", "scenes", "design_assets", "beat_list"
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
                       CREATE TABLE IF NOT EXISTS shots
                       (
                           id              INTEGER PRIMARY KEY AUTOINCREMENT,
                           project         TEXT,
                           scene           TEXT,
                           shot            TEXT,
                           shot_size       TEXT,
                           camera_angle    TEXT,
                           camera_movement TEXT,
                           lighting        TEXT,
                           description     TEXT,
                           prompt_path     TEXT,
                           image_path      TEXT,
                           version         INTEGER DEFAULT 1,
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
                           
                           version       INTEGER,
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
                           describe      TEXT NOT NULL,
                           image_path    TEXT NOT NULL,
                           prompt_path   TEXT,
                           version       INTEGER DEFAULT 1,
                           created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           UNIQUE (project, name, category)
                       );
                       ''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS beat_list
                       (
                           id            INTEGER PRIMARY KEY AUTOINCREMENT,
                           project       TEXT NOT NULL,
                           scene         TEXT NOT NULL,
                           beat_num      TEXT NOT NULL,
                           description   TEXT,
                           created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           UNIQUE (project, scene, beat_num)
                       );
                       ''')

        self.shared_conn.commit()

        self._migrate_scenes_table()
        self._migrate_design_assets_table()
        # self._migrate_scenes_image_path()  # Removed for Direction A
        # self._migrate_scenes_file_path()  # Removed for Direction A
        self._migrate_shots_status()
    
    def _migrate_shots_status(self):
        """Remove status column from shots table."""
        cursor = self.shared_conn.cursor()
        try:
            cursor.execute("SELECT status FROM shots LIMIT 1")
            print("🔧 Removing 'status' column from shots table...")
            try:
                cursor.execute("ALTER TABLE shots DROP COLUMN status")
                self.shared_conn.commit()
                print("✅ shots table updated (dropped status).")
            except Exception as e:
                print(f"⚠️ Migration warning (shots.status): {e}")
        except sqlite3.OperationalError:
            pass # Column already gone

    def _migrate_design_assets_table(self):
        """Migrate design_assets table: status -> version, remove attrs/remarks, add describe."""
        cursor = self.shared_conn.cursor()
        try:
            # Check if 'describe' column exists acts as flag for new schema
            cursor.execute("SELECT describe FROM design_assets LIMIT 1")
        except sqlite3.OperationalError:
            print("🔧 Migrating design_assets table structure (v2)...")
            try:
                # 1. Add describe column
                try:
                    cursor.execute("ALTER TABLE design_assets ADD COLUMN describe TEXT")
                except sqlite3.OperationalError: pass

                # 2. Add version/updated_at if missing (safety check)
                try:
                    cursor.execute("ALTER TABLE design_assets ADD COLUMN version INTEGER DEFAULT 1")
                except sqlite3.OperationalError: pass
                
                try:
                    cursor.execute("ALTER TABLE design_assets ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                except sqlite3.OperationalError: pass
                
                # 3. Drop obsolete columns
                # Note: SQLite dropped columns support added in 3.35.0
                for col in ['status', 'attributes', 'oss_url_cache', 'remarks']:
                    try:
                        cursor.execute(f"ALTER TABLE design_assets DROP COLUMN {col}")
                    except sqlite3.OperationalError: pass

                self.shared_conn.commit()
                print("✅ design_assets table migrated to new schema.")
            except Exception as e:
                print(f"⚠️ Migration warning: {e}")

    def _migrate_scenes_image_path(self):
        """Add image_path to scenes table if missing."""
        cursor = self.shared_conn.cursor()
        try:
            cursor.execute("SELECT image_path FROM scenes LIMIT 1")
        except sqlite3.OperationalError:
            print("🔧 Adding 'image_path' column to scenes table...")
            try:
                cursor.execute("ALTER TABLE scenes ADD COLUMN image_path TEXT")
                self.shared_conn.commit()
                print("✅ scenes table updated (added image_path).")
            except Exception as e:
                print(f"⚠️ Migration warning (scenes.image_path): {e}")

    def _migrate_scenes_file_path(self):
        """Add file_path to scenes table if missing."""
        cursor = self.shared_conn.cursor()
        try:
            cursor.execute("SELECT file_path FROM scenes LIMIT 1")
        except sqlite3.OperationalError:
            print("🔧 Adding 'file_path' column to scenes table...")
            try:
                cursor.execute("ALTER TABLE scenes ADD COLUMN file_path TEXT")
                self.shared_conn.commit()
                print("✅ scenes table updated (added file_path).")
            except Exception as e:
                print(f"⚠️ Migration warning (scenes.file_path): {e}")

    def _migrate_scenes_table(self):
        """迁移 scenes 表：删除 concept 字段，将 status 改为 version。"""
        cursor = self.shared_conn.cursor()
        cursor.execute("PRAGMA table_info(scenes)")
        cols = [row[1] for row in cursor.fetchall()]

        has_concept = "concept_url" in cols
        has_status = "status" in cols
        has_version = "version" in cols

        if not has_concept and not has_status and has_version:
            return

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS scenes_new
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
                           file_path     TEXT,
                           version       INTEGER,
                           created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           UNIQUE (project, scene)
                       );
                       ''')

        if has_status:
            cursor.execute("SELECT project, scene, world_prompt, elements, mood, color_tone, lighting_mood, characters, status, created_at, updated_at FROM scenes")
        else:
            cursor.execute("SELECT project, scene, world_prompt, elements, mood, color_tone, lighting_mood, characters, NULL as status, created_at, updated_at FROM scenes")
        rows = cursor.fetchall()

        def _parse_version(value):
            if value is None:
                return None
            if isinstance(value, int):
                return value
            text = str(value).strip().lower()
            if text.startswith("v") and text[1:].isdigit():
                return int(text[1:])
            if text.isdigit():
                return int(text)
            return None

        for row in rows:
            version = _parse_version(row[8])
            cursor.execute('''
                           INSERT OR REPLACE INTO scenes_new
                           (project, scene, world_prompt, elements, mood, color_tone, lighting_mood, characters, version, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ''',
                           (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], version, row[9], row[10]))

        cursor.execute("DROP TABLE scenes")
        cursor.execute("ALTER TABLE scenes_new RENAME TO scenes")
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

    def _generate_next_id(self, conn, table_name: str, id_column: str, prefix: str) -> str:
        """
        根据指定表和前缀，生成下一个补零的顺序ID
        例如 prefix 为 'p01-sc03-en'，如果库里最大为 'p01-sc03-en02'，则返回 'p01-sc03-en03'
        """
        cursor = conn.cursor()
        # 原生 SQL 匹配前缀最大值
        cursor.execute(f"SELECT {id_column} FROM {table_name} WHERE {id_column} LIKE ? ORDER BY {id_column} DESC LIMIT 1", (prefix + '%',))
        row = cursor.fetchone()
        
        if row and row[id_column]:
            max_id = row[id_column]
            # 提取最后两位(或多位)数字
            import re
            match = re.search(r'(\d+)$', max_id)
            if match:
                last_num = int(match.group(1))
                new_num = last_num + 1
            else:
                new_num = 1
        else:
            new_num = 1
            
        return f"{prefix}{new_num:02d}"

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

    def read_note(self, table_name: str, limit: int = 5, filter_conditions: dict = None) -> ToolResponse:
        """读取表中最近记录。"""
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

            sql += " ORDER BY id DESC LIMIT ?"
            params.append(int(limit))

            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            if not rows:
                return ToolResponse(content=[TextBlock(type="text", text=f"📭 表 '{table_name}' 无可读记录。")])

            result_list = [dict(row) for row in rows]
            json_result = json.dumps(result_list, ensure_ascii=False, indent=2)
            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 读取结果 ({len(rows)} 条):\n{json_result}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 读取异常: {str(e)}")])

    def save_to_note(self, table_name: str, data: dict) -> ToolResponse:
        """保存记录到指定表。"""
        return self.save_schedule(table_name, data)

    def query_note(self, table_name: str, filter_conditions: dict = None) -> ToolResponse:
        """
        查询指定表。
        :param table_name: 只能是以下表名之一: "tasks", "calendars", "projects", "patterns", "resources", "shots", "scenes", "design_assets", "beat_list", "mementos", "patterns_private"
        :param filter_conditions: 过滤条件字典
        """
        # 直接复用 read_note，但不限制只取极少条数，使用较大 limit 查询
        return self.read_note(table_name, limit=50, filter_conditions=filter_conditions)

    def delete_from_note(self, table_name: str, conditions: dict) -> ToolResponse:
        """从表中删除记录。"""
        return self.delete_schedule(table_name, conditions)

    def update_project_status(self, name: str, progress: str) -> ToolResponse:
        """更新项目进度。"""
        return self.save_project(name, progress)

    def get_latest_version(self, project: str, scene: str, shot: str) -> int:
        """获取指定镜头的最新版本号。"""
        cursor = self.shared_conn.cursor()
        cursor.execute('''
            SELECT MAX(version) AS max_ver
            FROM shots
            WHERE project=? AND uid=? AND shot=?
        ''', (project, scene, shot))
        row = cursor.fetchone()
        if not row or row[0] is None:
            return 0
        try:
            return int(row[0])
        except Exception:
            return 0

    def register_asset(self, project: str, scene: str, shot: str, prompt_path: str, version: int) -> ToolResponse:
        """登记资产到 production_assets。"""
        return self.save_shot(
            project=project,
            scene=scene,
            shot=shot,
            version=version,
            prompt_file_path=prompt_path,
            status="planning",
        )

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

    def save_scene(self, project: str, scene: str = None,
                   world_prompt: str = None,
                   elements: str = None,
                   mood: str = None,
                   color_tone: str = None,
                   lighting_mood: str = None,
                   characters: str = None,
                   version: int = None) -> ToolResponse:
        
        # 1. 自动派发符合规范的编号 p01-sc01
        import re
        prefix_str = f"{project}-sc"
        if not scene or not re.match(rf"^{prefix_str}\d+$", scene):
            scene = self._generate_next_id(self.shared_conn, 'scenes', 'uid', prefix_str)

        try:
            cursor = self.shared_conn.cursor()
            cursor.execute('SELECT id FROM scenes WHERE project=? AND uid=?', (project, scene))
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
                if version is not None: fields.append("version=?"); params.append(version)

                if not fields:
                    return ToolResponse(content=[TextBlock(type="text", text="⚠️ 场景表未发生变更 (未传入有效字段)")])

                fields.append("updated_at=CURRENT_TIMESTAMP")
                sql = f"UPDATE scenes SET {', '.join(fields)} WHERE id=?"
                params.append(row[0])
                self._execute_with_retry(self.shared_conn, sql, tuple(params))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 场景已更新: {scene}")])
            else:

                sql = '''INSERT INTO scenes (project, uid, world_prompt, elements, mood, color_tone, lighting_mood, characters, version)
                         
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'''
                self._execute_with_retry(self.shared_conn, sql,
                                         (project, scene, world_prompt, elements, mood, color_tone, lighting_mood,
                                          characters, version))
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
            cursor.execute('SELECT * FROM scenes WHERE project=? AND uid=?', (project, scene))
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
                    
                    f"🧾 Version: {('v' + str(data.get('version'))) if data.get('version') else 'unknown'}"
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
            sql = "DELETE FROM scenes WHERE project=? AND uid=?"
            cursor = self._execute_with_retry(self.shared_conn, sql, (project, scene))
            if cursor.rowcount > 0:
                return ToolResponse(content=[TextBlock(type="text", text=f"🗑️ 场景 '{scene}' 已删除。")])
            else:
                return ToolResponse(content=[TextBlock(type="text", text="⚠️ 未找到场景，删除无效。")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 删除场景失败: {e}")])

    def save_beat(self, project: str, scene: str, beat_num: str,
                  description: str = None) -> ToolResponse:
        """
        保存或更新节拍清单 (Beat List)
        """
        try:
            conn = self.shared_conn
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM beat_list WHERE project=? AND scene=? AND beat_num=?',
                           (project, scene, beat_num))
            row = cursor.fetchone()

            if row:
                if description:
                    sql = f"UPDATE beat_list SET description=?, updated_at=CURRENT_TIMESTAMP WHERE id=?"
                    self._execute_with_retry(conn, sql, (description, row[0]))
                    return ToolResponse(content=[TextBlock(type="text", text=f"✅ 节拍已更新: [{scene}-{beat_num}]")])
                else:
                    return ToolResponse(content=[TextBlock(type="text", text="⚠️ 无变更 (未提供 description)。")])
            else:
                sql = '''INSERT INTO beat_list (project, scene, beat_num, description)
                         VALUES (?, ?, ?, ?)'''
                params = (project, scene, beat_num, description)
                self._execute_with_retry(conn, sql, params)
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 节拍已创建: [{scene}-{beat_num}]")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Save Beat Error: {e}")])

    def save_beat_list(self, project: str, scene: str, beats: List[Dict[str, str]]) -> ToolResponse:
        """
        批量保存节拍清单 (Batch Save Beat List)
        :param beats: List of dicts, e.g., [{"beat_num": "1", "description": "..."}, {"beat_num": "2", "description": "..."}]
        """
        try:
            conn = self.shared_conn
            cursor = conn.cursor()
            success_count = 0
            
            # 使用事务进行批量操作
            for beat in beats:
                beat_num = beat.get("beat_num")
                description = beat.get("description")
                
                if not beat_num or not description:
                    continue

                cursor.execute('SELECT id FROM beat_list WHERE project=? AND scene=? AND beat_num=?',
                               (project, scene, beat_num))
                row = cursor.fetchone()

                if row:
                    sql = f"UPDATE beat_list SET description=?, updated_at=CURRENT_TIMESTAMP WHERE id=?"
                    self._execute_with_retry(conn, sql, (description, row[0]))
                else:
                    sql = '''INSERT INTO beat_list (project, scene, beat_num, description)
                             VALUES (?, ?, ?, ?)'''
                    self._execute_with_retry(conn, sql, (project, scene, beat_num, description))
                success_count += 1
                
            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 批量保存成功: 已处理 {success_count} 个节拍。")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Batch Save Error: {e}")])

    def get_beat_list(self, project: str, scene: str = None) -> ToolResponse:
        """
        获取节拍清单
        """
        try:
            conn = self.shared_conn
            cursor = conn.cursor()
            
            if scene:
                sql = "SELECT * FROM beat_list WHERE project=? AND scene=? ORDER BY beat_num ASC"
                params = (project, scene)
            else:
                sql = "SELECT * FROM beat_list WHERE project=? ORDER BY scene ASC, beat_num ASC"
                params = (project,)
                
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            if not rows:
                return ToolResponse(content=[TextBlock(type="text", text=f"📭 未找到节拍清单: {project} {scene or ''}")])
                
            result_list = [dict(row) for row in rows]
            return ToolResponse(content=[TextBlock(type="text", text=json.dumps(result_list, indent=2, ensure_ascii=False))])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Get Beat Error: {e}")])

    def save_shot(self, project: str, scene: str, shot: str = None,
                  description: str = None,
                  shot_size: str = None,
                  camera_angle: str = None,
                  camera_movement: str = None,
                  lighting: str = None,
                  prompt_file_path: str = None,
                  image_path: str = None,
                  # Compatibility args (ignored)
                  status: str = None,
                  version: int = 1) -> ToolResponse:
        
        # 1. 自动派发符合规范的编号 p01-sc01-sh01
        import re
        prefix_str = f"{scene}-sh"
        if not shot or not re.match(rf"^{prefix_str}\d+$", shot):
            shot = self._generate_next_id(self.shared_conn, 'shots', 'uid', prefix_str)

        try:
            cursor = self.shared_conn.cursor()
            cursor.execute('''
                           SELECT id
                           FROM shots
                           WHERE project = ?
                             AND scene = ?
                             AND uid = ?
                             AND version = ?
                           ''', (project, scene, shot, version))
            row = cursor.fetchone()

            if row:
                shot_id = row[0]
                fields = []
                params = []

                if description: fields.append("description=?"); params.append(description)
                if shot_size: fields.append("shot_size=?"); params.append(shot_size)
                if camera_angle: fields.append("camera_angle=?"); params.append(camera_angle)
                if camera_movement: fields.append("camera_movement=?"); params.append(camera_movement)
                if lighting: fields.append("lighting=?"); params.append(lighting)
                if prompt_file_path: fields.append("prompt_path=?"); params.append(prompt_file_path)
                # status field is removed

                if not fields:
                    return ToolResponse(content=[TextBlock(type="text", text="⚠️ 无字段变更。")])

                fields.append("updated_at=CURRENT_TIMESTAMP")
                sql = f"UPDATE shots SET {', '.join(fields)} WHERE id=?"
                params.append(shot_id)
                self._execute_with_retry(self.shared_conn, sql, tuple(params))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 镜头已更新: {shot} v{version}")])

            else:
                sql = '''
                      INSERT INTO shots (project, scene, uid, version, description, shot_size, camera_angle, camera_movement, lighting, prompt_path, image_path) \
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                      '''
                params = (
                    project, scene, shot, version, description, shot_size, camera_angle, camera_movement, lighting, prompt_file_path, image_path
                )
                self._execute_with_retry(self.shared_conn, sql, params)
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 镜头已创建: {shot} v{version}")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def save_shot_batch(self, project: str, scene: str, shots: List[Dict[str, str]]) -> ToolResponse:
        """
        批量保存镜头 (Batch Save Shots)
        :param shots: List of dicts, keys: shot, description, shot_size, camera_angle, camera_movement, lighting, prompt_path, image_path, version
        """
        try:
            conn = self.shared_conn
            cursor = conn.cursor()
            success_count = 0

            # 为批量镜头预先拿到当前场景的起始ID，方便连续派号
            import re
            prefix_str = f"{scene}-sh"
            
            # 使用现有最大值作为计数器起点，防止同一批里拿到相同的号
            cursor.execute(f"SELECT uid FROM shots WHERE uid LIKE ? ORDER BY uid DESC LIMIT 1", (prefix_str + '%',))
            max_row = cursor.fetchone()
            if max_row and max_row[0]:
                match = re.search(r'(\d+)$', max_row[0])
                current_max_num = int(match.group(1)) if match else 0
            else:
                current_max_num = 0

            for item in shots:
                shot = item.get("shot")
                
                # 如果没传，或者是乱写的名字，就派发连号
                if not shot or not re.match(rf"^{prefix_str}\d+$", shot):
                    current_max_num += 1
                    shot = f"{prefix_str}{current_max_num:02d}"
                    item["shot"] = shot # 更新回字典以便后续使用
                else:
                    # 如果传了正确的名字（如手动指定的某号），提取它的数字更新当前最大计数器，以免后续自增冲突
                    match = re.search(r'(\d+)$', shot)
                    if match and int(match.group(1)) > current_max_num:
                        current_max_num = int(match.group(1))

                version = item.get("version", 1)
                
                cursor.execute('''
                           SELECT id
                           FROM shots
                           WHERE project = ?
                             AND scene = ?
                             AND uid = ?
                             AND version = ?
                           ''', (project, scene, shot, version))
                row = cursor.fetchone()

                description = item.get("description")
                shot_size = item.get("shot_size")
                camera_angle = item.get("camera_angle")
                camera_movement = item.get("camera_movement")
                lighting = item.get("lighting")
                prompt_file_path = item.get("prompt_path")
                image_path = item.get("image_path")
                # status field is removed

                if row:
                    shot_id = row[0]
                    fields = []
                    params = []

                    if description: fields.append("description=?"); params.append(description)
                    if shot_size: fields.append("shot_size=?"); params.append(shot_size)
                    if camera_angle: fields.append("camera_angle=?"); params.append(camera_angle)
                    if camera_movement: fields.append("camera_movement=?"); params.append(camera_movement)
                    if lighting: fields.append("lighting=?"); params.append(lighting)
                    if prompt_file_path: fields.append("prompt_path=?"); params.append(prompt_file_path)

                    if fields:
                        fields.append("updated_at=CURRENT_TIMESTAMP")
                        sql = f"UPDATE shots SET {', '.join(fields)} WHERE id=?"
                        params.append(shot_id)
                        self._execute_with_retry(conn, sql, tuple(params))
                else:
                    sql = '''
                          INSERT INTO shots (project, scene, uid, version, description, shot_size, camera_angle, camera_movement, lighting, prompt_path, image_path) \
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                          '''
                    params = (
                        project, scene, shot, version, description, shot_size, camera_angle, camera_movement, lighting, prompt_file_path, image_path
                    )
                    self._execute_with_retry(conn, sql, params)
                success_count += 1

            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 批量镜头保存成功: 已处理 {success_count} 个镜头。")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Batch Save Shots Error: {e}")])

    def get_shot(self, project: str, scene: str, shot: str, version: int = None) -> ToolResponse:
        try:
            cursor = self.shared_conn.cursor()
            if version:
                sql = "SELECT * FROM shots WHERE project=? AND scene=? AND uid=? AND version=?"
                params = (project, scene, shot, version)
            else:
                sql = "SELECT * FROM shots WHERE project=? AND scene=? AND uid=? ORDER BY version DESC LIMIT 1"
                params = (project, scene, shot)

            rows = cursor.execute(sql, params).fetchall()

            result_data = []
            for row in rows:
                item = dict(row)
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
                sql = "DELETE FROM shots WHERE project=? AND uid=? AND shot=? AND version=?"
                params = (project, scene, shot, version)
            else:
                sql = "DELETE FROM shots WHERE project=? AND uid=? AND shot=?"
                params = (project, scene, shot)

            cursor = self._execute_with_retry(self.shared_conn, sql, params)
            return ToolResponse(content=[TextBlock(type="text", text=f"🗑️ 已删除 {cursor.rowcount} 条镜头记录。")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 删除镜头失败: {e}")])

    def save_design_asset(self, project: str, category: str,
                          describe: str,
                          image_path: str,
                          scene: str = None,
                          shot: str = None,
                          name: str = None,
                          prompt_file_path: str = None,
                          # Compatibility args (ignored)
                          attributes: str = None,
                          remarks: str = None,
                          status: str = None 
                          ) -> ToolResponse:
        
        if not describe or not image_path:
             return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: 'describe' and 'image_path' are mandatory fields for design assets.")])

        # 1. 强制映射分类到合法前缀白名单
        PREFIX_MAP = {
            "environment": "en", "en": "en",
            "character": "ch", "ch": "ch",
            "prop": "pr", "pr": "pr"
        }
        type_prefix = PREFIX_MAP.get(category.lower())
        if not type_prefix:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: 非法的 category '{category}'。仅允许 environment/en, character/ch, prop/pr")])

        # 2. 严选组装前缀 (例如: p01, 或 p01-sc03)
        parts = [project]
        if scene: parts.append(scene)
        if shot: parts.append(shot)
        
        # 3. 拼接资产类型前缀 (例如: p01-sc03-en 或 全局的 p01-ch)
        prefix_str = f"{'-'.join(parts)}-{type_prefix}"
        
        # 4. 如果没有传正确的强制编号（前缀+数字结尾），则由发号器自动分配
        import re
        if not name or not re.match(rf"^{prefix_str}\d+$", name):
            name = self._generate_next_id(self.shared_conn, 'design_assets', 'uid', prefix_str)

        try:
            cursor = self.shared_conn.cursor()
            cursor.execute('SELECT id, version FROM design_assets WHERE project=? AND category=? AND uid=?',
                           (project, category, name))
            row = cursor.fetchone()

            if row:
                current_version = row['version'] if row['version'] else 1
                new_version = current_version + 1
                
                fields = ["version=?, updated_at=CURRENT_TIMESTAMP"]
                params = [new_version]
                
                # Update core fields
                fields.append("describe=?"); params.append(describe)
                fields.append("image_path=?"); params.append(image_path)
                
                if prompt_file_path: fields.append("prompt_path=?"); params.append(prompt_file_path)

                sql = f"UPDATE design_assets SET {', '.join(fields)} WHERE id=?"
                params.append(row['id'])
                self._execute_with_retry(self.shared_conn, sql, tuple(params))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 资产已更新: {name} ({category}) v{new_version}")])
            else:
                sql = '''INSERT INTO design_assets (project, category, uid, describe, image_path, prompt_path, version)
                         VALUES (?, ?, ?, ?, ?, ?, ?)'''
                params = (project, category, name, describe, image_path, prompt_file_path, 1)
                self._execute_with_retry(self.shared_conn, sql, params)
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 新资产已登记: {name} ({category}) v1")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])

    def save_character(self, project: str, name: str = None,
                       describe: str = None,
                       image_path: str = None,
                       scene: str = None,
                       prompt_file_path: str = None,
                       # Compatibility args
                       attributes: str = None,
                       status: str = None,
                       remarks: str = None) -> ToolResponse:
        return self.save_design_asset(
            project=project,
            category="character",
            name=name,
            describe=describe,
            image_path=image_path,
            scene=scene,
            prompt_file_path=prompt_file_path,
        )

    def get_design_asset(self, project: str, category: str, name: str) -> ToolResponse:
        try:
            PREFIX_MAP = {
                "environment": "en", "en": "en",
                "character": "ch", "ch": "ch",
                "prop": "pr", "pr": "pr"
            }
            mapped_category = PREFIX_MAP.get(category.lower(), category.lower())
            
            # 1. First, try to query exact match in design_assets table
            cursor = self.shared_conn.cursor()
            cursor.execute('SELECT * FROM design_assets WHERE project=? AND (category=? OR category=?) AND name=?',
                           (project, category, mapped_category, name))
            row = cursor.fetchone()
            
            if row:
                return ToolResponse(content=[TextBlock(type="text", text=json.dumps(dict(row), indent=2, ensure_ascii=False))])
            
            # 2. Fallback: If querying environment, also check 'scenes' table
            # Agents often confuse "Environment Design Asset" with "Scene Concept Image"
            if category.lower() in ["environment", "scene", "bg", "background"]:
                # Try to find a scene with this name
                cursor.execute('SELECT * FROM scenes WHERE project=? AND uid=?', (project, name))
                scene_row = cursor.fetchone()
                if scene_row:
                    scene_data = dict(scene_row)
                    # Construct a fake design asset from scene data
                    virtual_asset = {
                        "id": f"scene_{scene_data['id']}",
                        "project": project,
                        "name": scene_data['scene'],
                        "category": "environment",
                        "describe": f"[From Scene Concept] Mood: {scene_data.get('mood')}. World: {scene_data.get('world_prompt')}",
                        "image_path": scene_data.get('image_path', ''),
                        "version": scene_data.get('version', 1),
                        "source": "derived_from_scenes_table" 
                    }
                    return ToolResponse(content=[TextBlock(type="text", text=json.dumps(virtual_asset, indent=2, ensure_ascii=False))])

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

    def get_dashboard(self, project: str = None, scene: str = None) -> ToolResponse:
        """
        仪表盘：获取当前工作台的状态，包括任务、项目、场景和资产信息。
        如果指定了 project/scene，会显示详细信息。
        如果不指定，会显示全局概览（包含所有项目列表）。
        """
        try:
            shared_cursor = self.shared_conn.cursor()
            private_cursor = self.private_conn.cursor()
            
            lines = []
            
            # --- 1. Global Index (Always fetch available projects to guide the agent) ---
            # 这一步是为了防止 Agent 搞错项目名称，总是把系统里的真实项目名列出来
            shared_cursor.execute("SELECT DISTINCT project FROM scenes UNION SELECT DISTINCT project FROM design_assets")
            all_projects = [r[0] for r in shared_cursor.fetchall() if r[0]]
            
            # --- 2. Smart Context Check ---
            # 如果用户传了 project 但不在库里，可能是拼写错误或大小写问题
            target_project = project
            if project:
                # 简单的大小写模糊匹配
                matched = next((p for p in all_projects if p.lower() == project.lower()), None)
                if matched and matched != project:
                    lines.append(f"⚠️ [Typo Correction] 输入的项目 '{project}' 未找到，自动修正为: '{matched}'")
                    target_project = matched
                elif not matched and project not in all_projects:
                    lines.append(f"⚠️ [Warning] 项目 '{project}' 在数据库中不存在。现有项目: {all_projects}")
            
            # --- 3. View Construction ---
            if target_project and scene:
                lines.append(f"🎬 === 项目工作台: {target_project} / {scene} ===")

                # 3.1 Scene Info
                shared_cursor.execute(
                    "SELECT world_prompt, elements, characters, version, image_path, mood FROM scenes WHERE project=? AND uid=?",
                    (target_project, scene))
                row = shared_cursor.fetchone()
                
                # 如果找不到 Scene，尝试模糊匹配
                if not row:
                     shared_cursor.execute("SELECT scene FROM scenes WHERE project=?", (target_project,))
                     exist_scenes = [r[0] for r in shared_cursor.fetchall()]
                     lines.append(f"❌ 场景 '{scene}' 未找到。")
                     lines.append(f"📋 该项目下的已知场景: {exist_scenes}")
                else:
                    lines.append("\n[场景设定 Scene Setup]")
                    lines.append(f"- Mood: {row['mood'] or '(Empty)'}")
                    lines.append(f"- Version: v{row['version'] or '?'}")
                    lines.append(f"- Concept Image: {row['image_path'] or '❌ (Missing)'}")
                    
                # 3.2 Design Assets (Environment/Characters)
                lines.append("\n[相关资产 Assets]")
                shared_cursor.execute(
                    "SELECT name, category, version, image_path FROM design_assets WHERE project=?",
                    (target_project,))
                assets = shared_cursor.fetchall()
                if assets:
                    for a in assets:
                         status_icon = "✅" if a['image_path'] else "⏳"
                         lines.append(f"- [{a['category']}] {a['name']} (v{a['version']}) {status_icon}")
                else:
                    lines.append("(暂无设计资产)")

                # 3.3 Shots
                lines.append("\n[镜头列表 Shots]")
                shared_cursor.execute('''
                               SELECT shot, version, description
                               FROM shots
                               WHERE project = ? AND scene = ?
                               ORDER BY cast(shot as integer) ASC, version DESC
                               ''', (target_project, scene))
                shot_rows = shared_cursor.fetchall()
                if shot_rows:
                    shots_seen = set()
                    for r in shot_rows:
                        if r['shot'] not in shots_seen:
                            lines.append(f"- Shot {r['shot']} (v{r['version']}): {r['description'][:30]}...")
                            shots_seen.add(r['shot'])
                else:
                    lines.append("(暂无镜头)")

            elif target_project:
                lines.append(f"🚀 === 项目概览: {target_project} ===")
                lines.append(f"📚 [场景列表] (Scenes)")
                shared_cursor.execute("SELECT scene, version, updated_at FROM scenes WHERE project=? ORDER BY scene ASC",
                               (target_project,))
                scene_rows = shared_cursor.fetchall()
                if scene_rows:
                    for r in scene_rows:
                        lines.append(f"- {r['scene']} (v{r['version']})")
                else:
                    lines.append("(暂无场景)")
                
                lines.append(f"\n🎨 [资产库] (Assets)")
                shared_cursor.execute("SELECT name, category FROM design_assets WHERE project=?", (target_project,))
                asset_rows = shared_cursor.fetchall()
                for r in asset_rows:
                    lines.append(f"- {r['category']}: {r['name']}")

            else:
                lines.append("👋 === 全局概览 (Global View) ===")
                
                lines.append("\n🌍 [现有项目 Projects]")
                if all_projects:
                    for p in all_projects:
                        lines.append(f"- {p}")
                else:
                    lines.append("(暂无项目)")

                lines.append("\n📋 [你的任务 Tasks]")
                shared_cursor.execute(
                    "SELECT id, content, priority FROM tasks WHERE agent_name=? AND status='todo' ORDER BY priority ASC LIMIT 5",
                    (self.agent_name,))
                task_rows = shared_cursor.fetchall()
                for r in task_rows:
                     prio = "🔥" if r['priority'] < 2 else ""
                     lines.append(f"- {prio}[ID:{r['id']}] {r['content']}")
                if not task_rows: lines.append("(无待办任务)")

            # Add Mementos at the end
            lines.append("\n🧠 [近期备忘 Mementos]")
            private_cursor.execute(
                "SELECT content, created_at FROM mementos WHERE agent_name=? ORDER BY id DESC LIMIT 3",
                (self.agent_name,))
            mementos = private_cursor.fetchall()
            for m in mementos:
                lines.append(f"- {m['content'][:100]}...")

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
