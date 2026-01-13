import sqlite3
import os
import time
import datetime
from typing import List, Dict, Optional

import json
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock


class AgentNotebook:

    def __init__(self, agent_name: str, db_name: str = "agent_notes.db"):
        self.agent_name = agent_name

        # 1. 确定存储路径
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.data_dir = os.path.join(base_dir, "data")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        self.db_path = os.path.join(self.data_dir, db_name)

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

        # === 6.媒资资产表 (production_assets) ===
        # 核心作用：连接“物理文件路径”与“逻辑状态”
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS production_assets
                       (
                           id             INTEGER PRIMARY KEY AUTOINCREMENT,
                           project        TEXT NOT NULL,                   -- 项目名 (如: WanderingEarth3)
                           scene          TEXT NOT NULL,                   -- 场 (如: Scene_01)
                           shot           TEXT NOT NULL,                   -- 镜 (如: Shot_05)
                           version        INTEGER   DEFAULT 1,             -- 版本号

                           prompt_path    TEXT,                            -- 提示词文件的绝对路径
                           image_path     TEXT,                            -- 图片文件的绝对路径 (生成后回填)

                           status         TEXT      DEFAULT 'pending_gen', -- 状态机: pending_gen -> generated -> audited
                           audit_feedback TEXT,                            -- 审核意见

                           created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                       )
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
    # 📝 写入工具 (Write Tools)
    # =================================================
    def save_to_note(self, table_name: str, data: dict) -> ToolResponse:
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

    def register_asset(self, project: str, scene: str, shot: str, prompt_path: str, version: int = 1) -> ToolResponse:
        """
        [资产注册] 在数据库中创建新的资产索引记录。

        当物理文件创建完成后，调用此方法在 SQLite 的 `production_assets` 表中记录该资产
        的元数据。此时资产状态将被初始化为 'pending_gen' (待生成)。

        Args:
            project (str): 项目名称。
            scene (str): 场次代码。
            shot (str): 镜头代码。
            prompt_path (str): 对应的 prompt.json 文件的绝对路径。
            version (int, optional): 版本号。默认为 1。

        Returns:
            ToolResponse: 包含新生成的资产 ID 的响应对象。
                          Content 示例: "✅ 资产已注册 ID: 42 (Status: pending_gen)"
        """
        try:
            sql = '''
                  INSERT INTO production_assets (project, scene, shot, version, prompt_path, status)
                  VALUES (?, ?, ?, ?, ?, 'pending_gen') \
                  '''
            cursor = self._execute_with_retry(sql, (project, scene, shot, version, prompt_path))
            asset_id = cursor.lastrowid
            return ToolResponse(
                content=[TextBlock(type="text", text=f"✅ 资产已注册 ID: {asset_id} (Status: pending_gen)")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 注册失败: {e}")])

    # =================================================
    # 📖 读取工具 (Read Tools)
    # =================================================

    def query_note(self, table_name: str, filter_conditions: dict = None) -> ToolResponse:
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

    def read_note(self) -> ToolResponse:
        """读取笔记本内容"""
        cursor = self.conn.cursor()
        lines = []

        # Tasks
        lines.append(f"\n📝 === 待办任务 (Tasks) ===")
        # 👈 SQL 查询改为了 lark_id
        cursor.execute(
            "SELECT id, content, lark_id, due_date FROM tasks WHERE agent_name=? AND status='todo' ORDER BY priority ASC",
            (self.agent_name,))
        rows = cursor.fetchall()
        if rows:
            for r in rows:
                # 👈 读取结果改为了 r['lark_id']
                lark_mark = f"[Lark:{r['lark_id'][-4:]}]" if r['lark_id'] else ""
                lines.append(f"- [ ] ID:{r['id']} {lark_mark} {r['content']} (Due: {r['due_date']})")
        else:
            lines.append("(无待办)")

        # Calendars
        lines.append(f"\n📅 === 近期日程 (Calendars) ===")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "SELECT content, start_time, end_time, lark_event_id FROM calendars WHERE agent_name=? AND end_time > ? ORDER BY start_time ASC LIMIT 20",
            (self.agent_name, now_str))
        rows = cursor.fetchall()
        if rows:
            for r in rows:
                lines.append(f"- 🕒 {r['start_time']} | {r['content']}")
        else:
            lines.append("(近期无日程)")

        # Mementos
        lines.append(f"\n🧠 === 自我交代 (Last 3 Mementos) ===")
        cursor.execute("SELECT content, created_at FROM mementos WHERE agent_name=? ORDER BY id DESC LIMIT 3",
                       (self.agent_name,))
        rows = cursor.fetchall()
        if rows:
            for r in rows:
                lines.append(f"- [{r['created_at'][:16]}] {r['content']}")
        else:
            lines.append("(空)")

        # Projects
        lines.append(f"\n🚀 === 项目进度 (Projects) ===")
        cursor.execute("SELECT name, progress FROM projects WHERE agent_name=?", (self.agent_name,))
        rows = cursor.fetchall()
        if rows:
            for r in rows:
                lines.append(f"- 【{r['name']}】: {r['progress']}")
        else:
            lines.append("(无活跃项目)")

        # Patterns
        lines.append(f"\n💡 === 行为规律 (Patterns - Top 5) ===")
        cursor.execute("SELECT content, hit_count FROM patterns WHERE agent_name=? ORDER BY hit_count DESC LIMIT 5",
                       (self.agent_name,))
        rows = cursor.fetchall()
        if rows:
            for r in rows:
                lines.append(f"- [Hit:{r['hit_count']}] {r['content']}")
        else:
            lines.append("(暂无)")

        return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

    def get_latest_version(self, project: str, scene: str, shot: str) -> int:
        """
        [版本查询] 获取指定镜头的当前最大版本号。

        用于在创建新版本前，查询数据库中已存在的最大版本号，以便计算下一个版本号（max + 1）。
        如果数据库中没有任何记录，则返回 0。

        Args:
            project (str): 项目名称。
            scene (str): 场次代码。
            shot (str): 镜头代码。

        Returns:
            int: 当前最大的版本号整数。如果未找到记录，返回 0。
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT MAX(version) FROM production_assets WHERE project=? AND scene=? AND shot=?",
            (project, scene, shot)
        )
        row = cursor.fetchone()
        return row[0] if row[0] else 0


    # =================================================
    # 🗑️ 删除工具 (Delete Tool) - 新增
    # =================================================

    def delete_from_note(self, table_name: str, conditions: dict) -> ToolResponse:
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

    # =================================================
    # ⚙️ 其他辅助方法 (修复 Missing Methods)
    # =================================================

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

    def update_task_status(self, task_id: int, status: str) -> ToolResponse:
        self._execute_with_retry("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
        return ToolResponse(content=[TextBlock(type="text", text="✅ Status Updated")])

    def update_project_status(self, project_name: str, progress: str) -> ToolResponse:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE agent_name=? AND name=?", (self.agent_name, project_name))
        row = cursor.fetchone()
        if row:
            self._execute_with_retry("UPDATE projects SET progress=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                                     (progress, row['id']))
        else:
            self._execute_with_retry("INSERT INTO projects (agent_name, name, progress) VALUES (?, ?, ?)", (self.agent_name, project_name, progress))
        return ToolResponse(content=[TextBlock(type="text", text="✅ Project Updated")])

    def close(self):
        if self.conn:
            self.conn.close()