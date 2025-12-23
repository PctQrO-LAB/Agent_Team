import os
import datetime
import pytz
from typing import Any, Dict

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# --- 1. 基础配置 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
CREDENTIALS_FILE = os.path.join(project_root, 'credentials.json')
TOKEN_FILE = os.path.join(project_root, 'token.json')

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks'
]


# --- 2. 辅助函数 (Helpers) ---

def _success_response(text: str, **metadata) -> ToolResponse:
    """✅ 快速返回成功结果"""
    return ToolResponse(
        content=[TextBlock(type="text", text=text)],
        metadata={"success": True, **metadata}
    )


def _error_response(text: str, error: Exception, **extra) -> ToolResponse:
    """❌ 快速返回错误结果"""
    return ToolResponse(
        content=[TextBlock(type="text", text=text)],
        metadata={"success": False, "error": str(error), **extra}
    )


def _get_service(service_name: str, version: str):
    """通用服务生成器"""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(f"❌ 找不到 {CREDENTIALS_FILE}，请确认文件路径。")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return build(service_name, version, credentials=creds)


def _get_my_timezone() -> str:
    try:
        service = _get_service('calendar', 'v3')
        setting = service.settings().get(setting='timezone').execute()
        return setting['value']
    except:
        return 'Asia/Shanghai'


def _to_utc_iso(local_time_str: str, user_tz_name: str) -> str:
    tz = pytz.timezone(user_tz_name)
    dt = datetime.datetime.strptime(local_time_str, "%Y-%m-%d %H:%M")
    dt_local = tz.localize(dt)
    dt_utc = dt_local.astimezone(pytz.utc)
    return dt_utc.strftime('%Y-%m-%dT%H:%M:%S.000Z')


# ==========================================
#              核心工具箱
# ==========================================

def get_calendar_events(limit: int = 20, **kwargs) -> ToolResponse:
    """
    获取用户的Google日历日程列表。

    从用户的主日历中获取即将到来的日程事件，从当前时间开始，按开始时间排序。
    输出格式经过特别优化，用于帮助 Agent 区分日程类型：
    - 「已锁定」([已锁])：具体时间段的日程，通常不应随意变动。
    - 「待排」([待排])：全天日程，通常视为待安排的任务池。

    Args:
        limit: (可选) 返回的日程数量上限，默认为 20 条。建议范围 1-50。

    Returns:
        ToolResponse: 标准工具响应对象。
        - content: 格式化后的文本列表，例如 "- [已锁] 2025-12-14 14:00 | 开会 (ID: ...)"。
        - metadata:
            - success (bool): 读取是否成功。
            - event_count (int): 日程总数。
            - events (list): 包含 id 和 summary 的结构化数据列表，方便程序进一步处理。
    """
    try:
        service = _get_service('calendar', 'v3')
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        events_result = service.events().list(
            calendarId='primary', timeMin=now, maxResults=limit,
            singleEvents=True, orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            return _success_response("📅 日程空空如也。", event_count=0, events=[])

        output = "📅 日程列表:\n"
        for event in events:
            eid = event['id']
            summary = event.get('summary', '无标题')
            start = event['start']

            if 'dateTime' in start:
                dt_str = start['dateTime']
                time_part = dt_str[11:16]
                date_part = dt_str[:10]
                output += f"- [已锁] {date_part} {time_part} | {summary} (ID: {eid})\n"
            else:
                date_part = start['date']
                output += f"- [待排] {date_part} (全天) | {summary} (ID: {eid})\n"

        return _success_response(
            output,
            event_count=len(events),
            events=[{"id": e['id'], "summary": e.get('summary', '无标题')} for e in events]
        )

    except Exception as e:
        return _error_response(f"❌ 读日历失败: {e}", e)


def add_calendar_event(summary: str, start_time: str, end_time: str = None,
                       reminder_minutes: int = None, **kwargs) -> ToolResponse:
    """
    在 Google Calendar 创建一个具体时间段的日程。

    这是一个**单一职责**的工具，它只负责在日历上锁定时间块，防止时间冲突。

    Args:
        summary: 日程标题（例如 "写代码"）。
        start_time: 开始时间，格式严格为 "YYYY-MM-DD HH:MM"（例如 "2025-12-14 14:00"）。
        end_time: (可选) 结束时间，格式同上。
                  如果不填，系统将默认根据开始时间自动推算（通常为 +30 分钟）。
        reminder_minutes: (可选) 提前多少分钟提醒。
                          - 0: 准点提醒
                          - 15: 提前15分钟
                          - 60: 提前1小时
                          - None: 使用日历默认配置

    Returns:
        ToolResponse: 执行结果响应。
        - content: 包含创建成功的确认信息。
        - metadata:
            - success (bool): 操作是否成功。
            - action (str): 固定为 "create_event"。
            - event_id (str): 新建的日历日程 ID。
            - summary (str): 日程标题。
    """
    try:
        # Step 1: 准备
        calendar_service = _get_service('calendar', 'v3')
        tz = _get_my_timezone()

        if not end_time:
            dt_start = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M")
            dt_end = dt_start + datetime.timedelta(minutes=30)
            end_time = dt_end.strftime("%Y-%m-%d %H:%M")

        # Step 2: 写日历
        event_body: Dict[str, Any] = {
            'summary': summary,
            'start': {'dateTime': start_time.replace(' ', 'T') + ':00', 'timeZone': tz},
            'end': {'dateTime': end_time.replace(' ', 'T') + ':00', 'timeZone': tz}
        }
        if reminder_minutes is not None:
            event_body['reminders'] = {
                'useDefault': False,
                'overrides': [{'method': 'popup', 'minutes': int(reminder_minutes)}]
            }
        else:
            event_body['reminders'] = {'useDefault': True}

        created_event = calendar_service.events().insert(calendarId='primary', body=event_body).execute()

        # Step 3: 返回结果 (只含日历信息)
        remind_msg = f"(提前{reminder_minutes}分)" if reminder_minutes is not None else ""
        result_text = f"✅ 日程锁定成功: {summary} ({start_time}-{end_time}) {remind_msg}"

        return _success_response(
            result_text,
            action="create_event",
            event_id=created_event.get('id'),
            summary=summary
        )

    except Exception as e:
        return _error_response(f"❌ 创建日程失败: {e}", e)


def delete_calendar_event(event_id: str, **kwargs) -> ToolResponse:
    """
    永久删除指定的 Google 日历日程。

    此工具主要用于以下场景：
    1. **清理占位符**：当「待排」的全天日程被重新安排为具体时间段后，用于删除旧的全天日程。
    2. **取消日程**：当用户明确表示取消某个会议或任务时使用。

    Args:
        event_id: 要删除的日程唯一 ID。
                  (该 ID 必须从 get_calendar_events 工具的返回结果中精确获取)

    Returns:
        ToolResponse: 删除操作的结果。
        - content: 删除成功的确认文本。
        - metadata:
            - success (bool): 操作是否成功。
            - action (str): 固定为 "delete_event"。
            - event_id (str): 被删除的 ID。
    """
    try:
        service = _get_service('calendar', 'v3')
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return _success_response("🗑️ 旧日程已清理", action="delete_event", event_id=event_id)
    except Exception as e:
        return _error_response(f"❌ 删除失败: {e}", e, event_id=event_id)


def add_google_task(title: str, due_time: str = None, **kwargs) -> ToolResponse:
    """
    在 Google Tasks 中创建一个待办事项。

    此工具既可以用于创建独立的琐碎任务，也可以配合 `add_calendar_event` 使用。

    Args:
        title: 任务标题（例如 "写代码"）。
        due_time: (可选) 截止时间，格式为 "YYYY-MM-DD HH:MM"。
                  如果不填，将创建一个无具体时间的待办项。

    Returns:
        ToolResponse: 操作结果。
        - content: 创建成功的提示信息。
        - metadata:
            - success (bool): 是否成功。
            - action (str): 固定为 "create_task"。
            - task_id (str): 新建任务的 ID。
            - title (str): 任务标题。
    """
    try:
        service = _get_service('tasks', 'v1')
        task_body = {'title': title}

        if due_time:
            user_tz = _get_my_timezone()
            utc_timestamp = _to_utc_iso(due_time, user_tz)
            task_body['due'] = utc_timestamp

        created_task = service.tasks().insert(tasklist='@default', body=task_body).execute()

        return _success_response(
            f"✅ 任务凭证已生成: {title}",
            action="create_task",
            task_id=created_task.get('id'),
            title=title
        )
    except Exception as e:
        return _error_response(f"❌ Task添加失败: {e}", e)


def get_google_tasks(**kwargs) -> ToolResponse:
    """
    获取当前未完成的 Google Tasks 待办事项列表。

    此工具用于读取用户的「任务池」，它是日程规划的原材料来源。
    Agent 应定期调用此工具，检查是否有新添加的、尚未安排具体时间的任务。

    Returns:
        ToolResponse: 包含待办清单的响应。
        - content: 格式化的文本清单，例如 "- 买牛奶 (ID: ...)"。
        - metadata:
            - success (bool): 读取是否成功。
            - task_count (int): 未完成任务的数量。
            - tasks (list): 包含 id 和 title 的结构化列表，方便 Agent 遍历处理。
    """
    try:
        service = _get_service('tasks', 'v1')
        # ✅ 修改点：showCompleted=True, showHidden=True
        # hidden=True 确保即使用户在界面上清除了已完成任务，API 仍能拉取到近期记录
        results = service.tasks().list(
        tasklist='@default',
        showCompleted=True,
        showHidden=True,
        maxResults=50  # 建议加上数量限制，防止拉取几千条历史记录
        ).execute()

        items = results.get('items', [])

        if not items:
            return _success_response("📭 暂无任何任务记录。", task_count=0, tasks=[])

        out = "📝 任务清单:\n"
        task_list = []

        for t in items:
            status = t['status']  # 'needsAction' or 'completed'
            # 添加状态标记，方便 Agent 识别
            mark = "✅[已完]" if status == 'completed' else "⬜[待办]"
            out += f"- {mark} {t['title']} (ID: {t['id']})\n"

            task_list.append({
                "id": t['id'],
                "title": t['title'],
                "status": status  # 把状态也传给 Agent
            })

        return _success_response(
            out,
            task_count=len(items),
            tasks=task_list
        )
    except Exception as e:
        return _error_response(f"❌ 读任务失败: {e}", e)


def delete_google_task(task_id: str, **kwargs) -> ToolResponse:
    """
    永久删除指定的 Google Task（任务粉碎机）。

    Args:
        task_id: 要粉碎的任务 ID。
                 (必须严格来自 `get_google_tasks` 返回列表中的 ID)

    Returns:
        ToolResponse: 删除操作的结果。
        - content: 删除确认信息。
        - metadata:
            - success (bool): 操作是否成功。
            - action (str): 固定为 "delete_task"。
            - task_id (str): 被删除的任务 ID。
    """
    try:
        service = _get_service('tasks', 'v1')
        service.tasks().delete(tasklist='@default', task=task_id).execute()

        return _success_response(
            "🗑️ 任务已永久删除",
            action="delete_task",
            task_id=task_id
        )
    except Exception as e:
        return _error_response(f"❌ 任务删除失败: {e}", e, task_id=task_id)