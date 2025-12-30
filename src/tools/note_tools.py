import json
import os
import datetime
from typing import List, Dict, Optional
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock


class AgentNotebook:
    """
    Agent 专属笔记本工具类。
    用于管理本地的持久化记忆，包括：任务清单、日程记录、项目进度、行为规律以及自我交代(Memento)。
    """

    def __init__(self, agent_name: str):
        """
        初始化笔记本。
        自动检测是否存在历史文件：
        - 存在: 加载历史数据，并自动升级旧版数据结构。
        - 不存在: 初始化新笔记本。
        """
        self.agent_name = agent_name

        # 1. 确定存储路径 (确保在项目根目录的 data 文件夹下)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.data_dir = os.path.join(base_dir, "data")
        self.file_path = os.path.join(self.data_dir, f"notebook_{agent_name}.json")

        # 确保目录存在
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        # 2. 加载或新建
        if os.path.exists(self.file_path):
            self._load()
            print(f"📖 [Notebook] 发现历史存档，已加载: {self.file_path}")
        else:
            self._init_new()
            print(f"✨ [Notebook] 未发现存档，已新建: {self.file_path}")

    def _init_new(self):
        """初始化全新的数据结构"""
        self.data = {
            "meta": {
                "owner": self.agent_name,
                "created_at": str(datetime.datetime.now())
            },
            "mementos": [],  # 🧠 自我交代 (New: 独立存储)
            "tasks": [],  # 📝 待办任务 (Action Items)
            "calendars": [],  # 📅 日程记录 (New: 与任务分离)
            "projects": [],  # 🚀 项目进度
            "patterns": []  # 💡 规律总结
        }
        self._save()

    def _load(self):
        """加载 JSON 并自动修复/升级数据结构"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)

            # --- 🔥 核心修复与迁移逻辑 ---
            # 定义标准数据结构 (Schema)
            default_structure = {
                "meta": {
                    "owner": self.agent_name,
                    "created_at": str(datetime.datetime.now())
                },
                "mementos": [],
                "tasks": [],
                "calendars": [],  # 👈 确保这个新字段存在
                "projects": [],
                "patterns": []
            }

            data_changed = False
            for key, default_val in default_structure.items():
                if key not in loaded_data:
                    loaded_data[key] = default_val
                    data_changed = True

            self.data = loaded_data

            if data_changed:
                self._save()
                print(f"🔧 [Notebook] 数据结构已升级，补全了缺失字段 (如 calendars/mementos)。")

        except Exception as e:
            print(f"⚠️ 笔记本文件损坏，重置为空: {e}")
            self._init_new()

    def _save(self):
        """写入 JSON 到磁盘"""
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # =================================================
    # 📖 工具能力 (Tools)
    # =================================================

    def read_notebook(self) -> ToolResponse:
        """
        读取笔记本的所有内容。

        用途：
        在会话开始（复苏阶段）或需要回顾上下文时调用。
        内容包含：
        1. 【自我交代 (Mementos)】：你上一轮留给自己的关键信息。
        2. 【待办任务 (Tasks)】：当前的 To-Do List。
        3. 【日程记录 (Calendars)】：已安排的时间表。
        4. 【项目 (Projects)】：长期项目的当前状态。
        5. 【规律 (Patterns)】：已总结的用户偏好。
        """
        # 构造易读的文本视图，而不是直接 dump json
        lines = []

        # 1. Mementos (只显示最近 3 条，避免太长)
        lines.append(f"🧠 === 自我交代 (Last 3 Mementos) ===")
        mementos = self.data.get("mementos", [])[-3:]
        if mementos:
            for m in mementos:
                lines.append(f"- [{m['date']}] {m['content']}")
        else:
            lines.append("(空)")

        # 2. Tasks
        lines.append(f"\n📝 === 待办任务 (Tasks) ===")
        tasks = self.data.get("tasks", [])
        active_tasks = [t for t in tasks if t.get('status') != 'done']  # 只看未完成的
        if active_tasks:
            for t in active_tasks:
                lines.append(f"- [ ] ID:{t['id']} | {t['content']} (Due: {t.get('due', '无')})")
        else:
            lines.append("(无待办)")

        # 3. Calendars (New)
        lines.append(f"\n📅 === 日程记录 (Calendars) ===")
        cals = self.data.get("calendars", [])
        # 简单的按时间排序逻辑可以加在这里，目前先直接列出
        # 过滤掉已经过去的日程（比如只显示今天的和未来的）
        now_str = datetime.datetime.now().strftime("%Y-%m-%d")
        future_cals = [c for c in cals if c.get('start_time', '') >= now_str]

        if future_cals:
            for c in future_cals:
                lines.append(f"- 🕒 {c['start_time']} ~ {c['end_time']} | {c['content']} (ID:{c['id']})")
        else:
            lines.append("(近期无日程记录)")

        # 4. Projects
        lines.append(f"\n🚀 === 项目进度 (Projects) ===")
        projects = self.data.get("projects", [])
        if projects:
            for p in projects:
                lines.append(f"- 【{p['name']}】: {p['progress']}")
        else:
            lines.append("(无活跃项目)")

        # 5. Patterns
        lines.append(f"\n💡 === 行为规律 (Patterns - Top 5) ===")
        patterns = self.data.get("patterns", [])[-5:]
        if patterns:
            for p in patterns:
                lines.append(f"- {p['content']}")
        else:
            lines.append("(暂无)")

        return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

    def save_memento(self, content: str) -> ToolResponse:
        """
        [重点] 写入一条“自我交代”(Memento)。

        用途：
        在会话结束前，或者晚报结束时，强制调用此工具。
        将“下一步该做什么”、“当前思考到了哪一步”或者“明天早上醒来第一件事要注意什么”写下来。
        这是你跨越短期记忆（Context）清理的唯一桥梁！

        Args:
            content: 留给未来的自己的话。例如："明天早上优先检查流言论文的文献部分。"
        """
        new_memento = {
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "content": content
        }
        self.data["mementos"].append(new_memento)
        self._save()
        return ToolResponse(content=[TextBlock(type="text", text=f"✅ 已刻录自我交代: {content}")])

    def record_task(self, content: str, status: str = "todo", due_date: str = "无") -> ToolResponse:
        """
        记录一条【任务 (Action Item)】。

        注意：
        仅用于记录需要“执行”的动作，如“撰写报告”、“回复邮件”。
        如果是“参加会议”、“某段时间的安排”，请使用 record_calendar_event 工具。

        Args:
            content: 任务描述
            status: 状态 (todo / pending / done)
            due_date: 截止日期描述
        """
        task_id = f"T{len(self.data['tasks']) + 1}"
        new_task = {
            "id": task_id,
            "content": content,
            "status": status,
            "due": due_date,
            "created_at": str(datetime.datetime.now())
        }
        self.data['tasks'].append(new_task)
        self._save()
        return ToolResponse(content=[TextBlock(type="text", text=f"✅ 已记录任务 {task_id}: {content}")])

    def record_calendar_event(self, content: str, start_time: str, end_time: str) -> ToolResponse:
        """
        记录一条【日程 (Calendar Event)】。

        用途：
        当你调用飞书日历工具创建了日程后，务必也同步调用此工具记录在笔记本中，
        以便在生成晨报/日报时能快速读取，而不需要每次都查飞书 API。

        Args:
            content: 日程标题/主题
            start_time: 开始时间 (如 "2025-01-01 14:00")
            end_time: 结束时间
        """
        cal_id = f"C{len(self.data['calendars']) + 1}"
        new_event = {
            "id": cal_id,
            "content": content,
            "start_time": start_time,
            "end_time": end_time,
            "created_at": str(datetime.datetime.now())
        }
        self.data['calendars'].append(new_event)
        self._save()
        return ToolResponse(content=[TextBlock(type="text", text=f"✅ 已记录日程 {cal_id}: {content} ({start_time})")])

    def update_task_status(self, task_id: str, status: str) -> ToolResponse:
        """
        更新任务状态。

        Args:
            task_id: 任务ID (如 T1) 或 任务内容的关键词
            status: 新状态 (todo, done, pending, deleted)
        """
        for t in self.data['tasks']:
            # 支持精确匹配 ID 或 模糊匹配内容
            if t['id'] == task_id or (task_id in t['content']):
                old_status = t['status']
                t['status'] = status
                t['updated_at'] = str(datetime.datetime.now())
                self._save()
                return ToolResponse(
                    content=[TextBlock(type="text", text=f"✅ 任务 {t['id']} 状态已更新: {old_status} -> {status}")])

        return ToolResponse(content=[TextBlock(type="text", text=f"❌ 未找到任务: {task_id}")])

    def update_project_status(self, project_name: str, progress: str) -> ToolResponse:
        """
        更新或创建项目进度。

        Args:
            project_name: 项目名称
            progress: 当前进度描述
        """
        for p in self.data['projects']:
            if p['name'] == project_name:
                p['progress'] = progress
                p['updated_at'] = str(datetime.datetime.now())
                self._save()
                return ToolResponse(
                    content=[TextBlock(type="text", text=f"✅ 项目 '{project_name}' 更新为: {progress}")])

        # 新建项目
        self.data['projects'].append({
            "name": project_name,
            "progress": progress,
            "created_at": str(datetime.datetime.now())
        })
        self._save()
        return ToolResponse(content=[TextBlock(type="text", text=f"✅ 新项目 '{project_name}' 已创建: {progress}")])

    def add_pattern(self, observation: str) -> ToolResponse:
        """
        [晚报专用] 记录一条用户行为规律。

        Args:
            observation: 观察到的规律。例如："用户倾向于在周五下午安排低脑力负荷的工作。"
        """
        pattern_id = f"P{len(self.data['patterns']) + 1}"
        self.data['patterns'].append({
            "id": pattern_id,
            "content": observation,
            "date": str(datetime.datetime.now())
        })
        self._save()
        return ToolResponse(content=[TextBlock(type="text", text=f"✅ 规律已归档 {pattern_id}: {observation}")])

    def promote_pattern_to_memory(self, pattern_text: str) -> ToolResponse:
        """
        将重要规律标记为'需写入长期记忆'。
        """
        return ToolResponse(content=[TextBlock(type="text",
                                               text=f"🚀 建议操作：请立即调用 `record_to_memory` 工具(如有)或记录在 Memento 中，内容：\n{pattern_text}")])