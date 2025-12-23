import json
import os
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock


class AgentNotebook:
    def __init__(self, agent_name: str):
        self.file_path = os.path.join(os.getcwd(), "data", f"notebook_{agent_name}.json")
        self._ensure_storage()

    def _ensure_storage(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        # 初始化结构，确保所有键都存在
        if not os.path.exists(self.file_path):
            self._save({
                "normal_tasks": [],
                "supreme_schedules": [],
                "created_tasks_whitelist": []
            })
        else:
            # 如果文件存在但缺少字段（旧版本兼容），补全它
            data = self._load()
            changed = False
            for key in ["normal_tasks", "supreme_schedules", "created_tasks_whitelist"]:
                if key not in data:
                    data[key] = []
                    changed = True
            if changed:
                self._save(data)

    def _save(self, data):
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load(self) -> dict:
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except:
            return {"normal_tasks": [], "supreme_schedules": [], "created_tasks_whitelist": []}

    def _find_and_remove(self, task_list: list, task_id: str) -> bool:
        """内部辅助：从列表中查找并移除指定ID的项目（兼容旧的纯字符串ID和新的字典格式）"""
        for i, item in enumerate(task_list):
            # 兼容逻辑：如果是字典，检查 id 字段；如果是字符串（旧数据），直接比较
            current_id = item.get("id") if isinstance(item, dict) else item
            if current_id == task_id:
                task_list.pop(i)
                return True
        return False

    def _check_exists(self, task_list: list, task_id: str) -> bool:
        """内部辅助：检查ID是否存在"""
        for item in task_list:
            current_id = item.get("id") if isinstance(item, dict) else item
            if current_id == task_id:
                return True
        return False

    # === 🤖 暴露给 Agent 的工具 ===

    def read_notes(self) -> ToolResponse:
        """
        查阅当前笔记本中存储的所有任务和日程记录。

        当需要确认哪些任务已经被记录、哪些是不可变动的最高日程时使用此工具。
        它会返回当前的“最高日程”列表和“普通任务”列表，包含 ID 和名称。

        Returns:
            ToolResponse: 包含当前所有记录状态的工具响应对象。
        """
        data = self._load()

        def format_list(lst):
            # 格式化输出：将对象列表转为 "ID: 名称" 的易读字符串
            formatted = []
            for item in lst:
                if isinstance(item, dict):
                    formatted.append(f"{item.get('id')} ({item.get('name', '无标题')})")
                else:
                    # 兼容旧数据
                    formatted.append(f"{item} (旧数据)")
            return formatted

        supreme = format_list(data.get("supreme_schedules", []))
        normal = format_list(data.get("normal_tasks", []))

        msg_content = (
            f"📖 [笔记状态]:\n"
            f"👑 [最高日程 (不可动/High Priority)]: {supreme}\n"
            f"✅ [普通任务 (可调整/Normal)]: {normal}"
        )

        return ToolResponse(
            content=[TextBlock(type="text", text=msg_content)]
        )

    def write_note(self, id: str, name: str, is_supreme: bool = False) -> ToolResponse:
        """
        将一个任务 ID 和名称记录到笔记本中，或更新其状态。

        用于标记任务已处理，或者记录扫描到的新日程。
        如果该 ID 已存在于另一个列表中，它会被移动到当前指定的目标列表中。

        Args:
            id (str): 任务或日程的唯一标识符（ID）。
            name (str): 任务或日程的标题/名称（Summary）。
            is_supreme (bool, optional): 是否为“最高日程”（即固定时间、不可变动的日程）。
                                         默认为 False，表示记录为“普通任务”。

        Returns:
            ToolResponse: 操作结果的反馈信息。
        """
        data = self._load()
        target_key = "supreme_schedules" if is_supreme else "normal_tasks"
        other_key = "normal_tasks" if is_supreme else "supreme_schedules"

        target_list = data[target_key]
        other_list = data[other_key]

        # 1. 避免跨列表重复：如果在另一个列表里，先删掉
        self._find_and_remove(other_list, id)

        msg_content = ""

        # 2. 检查当前列表是否已存在
        # 我们先尝试移除旧的同ID记录（为了更新名称），然后再添加新的
        removed_in_target = self._find_and_remove(target_list, id)

        # 3. 添加新记录（包含 ID 和 Name）
        new_entry = {"id": id, "name": name}
        target_list.append(new_entry)
        self._save(data)

        tag = "👑 最高日程" if is_supreme else "✅ 普通任务"
        action = "更新" if removed_in_target else "标记"
        msg_content = f"✍️ 已{action}为 {tag}: {name} (ID: {id})"

        return ToolResponse(
            content=[TextBlock(type="text", text=msg_content)]
        )

    def record_created_task(self, task_id: str, task_name: str) -> ToolResponse:
        """
        将由 Agent 新创建的任务 ID 和名称记录到白名单中，防止在后续扫描中被误删。

        **使用场景**：
        每当调用 `add_google_task` 或 `add_calendar_event` 创建新项目后，必须立即调用此工具。
        这能起到“保护盾”的作用，防止该任务在随后的“清理旧项”逻辑中被错误地识别为需要删除的对象。

        Args:
            task_id (str): 刚刚创建的任务或日程的唯一标识符（ID）。
            task_name (str): 刚刚创建的任务名称。

        Returns:
            ToolResponse: 包含操作结果反馈的工具响应对象。
        """
        data = self._load()
        if "created_tasks_whitelist" not in data:
            data["created_tasks_whitelist"] = []

        msg_content = ""
        # 检查是否存在，如果存在则不重复添加 (或者可以选择更新名称)
        if not self._check_exists(data["created_tasks_whitelist"], task_id):
            data["created_tasks_whitelist"].append({"id": task_id, "name": task_name})
            self._save(data)
            msg_content = f"🛡️ Task '{task_name}' ({task_id}) 已加入白名单，后续扫描将忽略它。"
        else:
            msg_content = f"⚠️ Task {task_id} 已在白名单中。"

        return ToolResponse(
            content=[TextBlock(type="text", text=msg_content)]
        )

    def delete_note(self, id: str) -> ToolResponse:
        """
        从笔记本中彻底删除指定的 ID。

        当一个任务已经彻底完成、取消，或者发现该 ID 无效时使用此工具。
        这会从“最高日程”和“普通任务”中同时查找并移除该 ID。

        Args:
            id (str): 需要移除的任务或日程的唯一标识符（ID）。

        Returns:
            ToolResponse: 删除操作的结果反馈。
        """
        data = self._load()
        deleted = False

        # 尝试从两个列表中删除
        if self._find_and_remove(data["normal_tasks"], id):
            deleted = True
        if self._find_and_remove(data["supreme_schedules"], id):
            deleted = True
        # 也可以选择性地从白名单中删除，视逻辑而定，这里暂且保留或也删除
        if self._find_and_remove(data.get("created_tasks_whitelist", []), id):
            deleted = True

        msg_content = ""
        if deleted:
            self._save(data)
            msg_content = f"🗑️ 已从笔记中彻底移除: {id}"
        else:
            msg_content = f"⚠️ 笔记中找不到 ID: {id}"

        return ToolResponse(
            content=[TextBlock(type="text", text=msg_content)]
        )