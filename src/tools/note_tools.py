import sqlite3
import os
import time
import datetime
from typing import List, Dict, Optional
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock


class AgentNotebook:
    """
    Agent 专属的 SQLite 笔记本工具类 (v2.1 修复版)。

    更新日志：
    1. [Fix] 修复了缺少 promote_pattern_to_memory 导致的 AttributeError。
    2. [Schema] 将 tasks 表的 lark_task_id 重命名为 lark_id。
    3. [Stability] 保留了写入重试机制。
    """

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
        """初始化数据库表结构"""
        cursor = self.conn.cursor()

        # --- 1. Mementos ---
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS mementos
                       (
                           id         INTEGER PRIMARY KEY AUTOINCREMENT,
                           agent_name TEXT NOT NULL,
                           content    TEXT NOT NULL,
                           created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                       )
                       ''')

        # --- 2. Tasks (修改：lark_task_id -> lark_id) ---
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS tasks
                       (
                           id         INTEGER PRIMARY KEY AUTOINCREMENT,
                           agent_name TEXT NOT NULL,
                           lark_id    TEXT, -- 👈 已修改为 lark_id
                           content    TEXT NOT NULL,
                           status     TEXT      DEFAULT 'todo',
                           due_date   TEXT,
                           priority   INTEGER   DEFAULT 2,
                           created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           updated_at TIMESTAMP
                       )
                       ''')

        # --- 3. Calendars ---
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS calendars
                       (
                           id            INTEGER PRIMARY KEY AUTOINCREMENT,
                           agent_name    TEXT NOT NULL,
                           lark_event_id TEXT,
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

    # =================================================
    # 📝 写入工具 (Write Tools)
    # =================================================

    def record_task(self, content: str, lark_id: str = "", status: str = "todo", due_date: str = "无",
                    priority: int = 2) -> ToolResponse:
        """
        记录一条【任务 (Task)】。

        Args:
            content: 任务标题/内容 (请勿包含 LarkID！)
            lark_id: 飞书任务的 GUID (请填在这里，不要填在 content 里)
            status: 状态
            due_date: 截止日期
            priority: 优先级
        """
        # 👈 这里参数名和 SQL 都改为了 lark_id
        cursor = self._execute_with_retry(
            "INSERT INTO tasks (agent_name, content, lark_id, status, due_date, priority) VALUES (?, ?, ?, ?, ?, ?)",
            (self.agent_name, content, lark_id, status, due_date, priority)
        )
        return ToolResponse(
            content=[TextBlock(type="text", text=f"✅ 已记录任务 DB_ID:{cursor.lastrowid} | 飞书ID:{lark_id or '无'}")])

    def record_calendar_event(self, content: str, start_time: str, end_time: str,
                              lark_event_id: str = "") -> ToolResponse:
        """记录一条【日程 (Calendar)】。"""
        self._execute_with_retry(
            "INSERT INTO calendars (agent_name, content, start_time, end_time, lark_event_id) VALUES (?, ?, ?, ?, ?)",
            (self.agent_name, content, start_time, end_time, lark_event_id)
        )
        return ToolResponse(content=[TextBlock(type="text", text=f"✅ 已记录日程: {content}")])

    # =================================================
    # 📖 读取工具 (Read Tools)
    # =================================================

    def read_notebook(self) -> ToolResponse:
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
            "SELECT content, start_time, end_time, lark_event_id FROM calendars WHERE agent_name=? AND end_time > ? ORDER BY start_time ASC LIMIT 5",
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