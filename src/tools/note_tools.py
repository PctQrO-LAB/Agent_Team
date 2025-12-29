import json
import os
import datetime
from typing import List, Dict, Optional
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock


class AgentNotebook:
    def __init__(self, agent_name: str):
        """
        初始化笔记本。
        自动检测是否存在历史文件：
        - 存在: 加载历史数据
        - 不存在: 初始化新笔记本
        """
        self.agent_name = agent_name

        # 1. 确定存储路径 (确保在项目根目录的 data 文件夹下)
        # 获取当前文件 (src/tools/note_tools.py) 的上上上级目录 (项目根目录)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.data_dir = os.path.join(base_dir, "data")
        self.file_path = os.path.join(self.data_dir, f"notebook_{agent_name}.json")

        # 确保目录存在
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        # 2. 核心逻辑：加载或新建
        if os.path.exists(self.file_path):
            self._load()
            print(f"📖 [Notebook] 发现历史存档，已加载: {self.file_path}")
        else:
            self._init_new()
            print(f"✨ [Notebook] 未发现存档，已新建: {self.file_path}")

    def _init_new(self):
        """初始化数据结构"""
        self.data = {
            "meta": {
                "owner": self.agent_name,
                "created_at": str(datetime.datetime.now())
            },
            "tasks": [],  # 待办/已办任务
            "projects": [],  # 项目进度
            "patterns": [],  # 总结出的规律
            "mementos": []  # 每日自我交代
        }
        self._save()

    def _load(self):
        """加载 JSON (包含自动修复逻辑)"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)

            # --- 🔥 核心修复开始 ---
            # 定义标准数据结构
            default_structure = {
                "meta": {
                    "owner": self.agent_name,
                    "created_at": str(datetime.datetime.now())
                },
                "tasks": [],  # 确保这行存在
                "projects": [],  # 确保这行存在
                "patterns": [],
                "mementos": []
            }

            # 检查并补全缺失的 key (数据迁移逻辑)
            # 如果你的旧文件里没有 'tasks'，这里会自动给它加上一个空列表 []
            data_changed = False
            for key, default_val in default_structure.items():
                if key not in loaded_data:
                    loaded_data[key] = default_val
                    data_changed = True

            self.data = loaded_data

            # 如果发生了补全，立即存回文件，防止下次还缺
            if data_changed:
                self._save()
                print(f"🔧 [Notebook] 检测到旧格式数据，已自动修复缺失字段。")
            # --- 🔥 核心修复结束 ---

        except Exception as e:
            print(f"⚠️ 笔记本文件损坏，重置为空: {e}")
            self._init_new()

    def _save(self):
        """写入 JSON"""
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # =================================================
    # 📖 工具能力 (Tools)
    # =================================================

    def read_notebook(self) -> ToolResponse:
        """
        读取笔记本的所有内容。
        用于：审计当前状态、检查未完成任务、回顾之前的总结。
        """
        # 转换为易读的文本格式
        content = json.dumps(self.data, ensure_ascii=False, indent=2)
        return ToolResponse(content=[TextBlock(type="text", text=content)])

    def record_task(self, content: str, status: str = "todo", due_date: str = "无") -> ToolResponse:
        """
        记录一条新任务或日程备注。
        Args:
            content: 任务内容
            status: todo/done/pending
            due_date: 截止时间描述
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

    def update_task_status(self, task_id: str, status: str) -> ToolResponse:
        """更新任务状态 (如把 todo 改为 done)"""
        for t in self.data['tasks']:
            if t['id'] == task_id or task_id in t['content']:  # 模糊匹配 ID 或内容
                old_status = t['status']
                t['status'] = status
                t['updated_at'] = str(datetime.datetime.now())
                self._save()
                return ToolResponse(
                    content=[TextBlock(type="text", text=f"✅ 任务 {t['id']} 状态已更新: {old_status} -> {status}")])

        return ToolResponse(content=[TextBlock(type="text", text=f"❌ 未找到任务 ID: {task_id}")])

    def update_project_status(self, project_name: str, progress: str) -> ToolResponse:
        """更新项目进度"""
        # 查找现有项目
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
        [晚报专用] 记录一条用户行为规律或反思。
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
        将一条重要规律标记为'需写入长期记忆'。
        注意：Agent 收到此返回后，应主动调用 `record_to_memory` 工具。
        """
        # 这里我们只做一个回显，提示 Agent 去调用 Mem0 的工具
        return ToolResponse(content=[TextBlock(type="text",
                                               text=f"🚀 建议操作：请立即调用 `record_to_memory` 工具，将以下内容存入向量数据库：\n{pattern_text}")])