import os
import base64
import json
import datetime
import logging
from typing import List, Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    GetMessageResourceRequest,
)
from lark_oapi.api.drive.v1 import (
    DownloadFileRequest,
    ListFileRequest,
    UploadAllFileRequest,
    UploadAllFileRequestBody,
)
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock
from src.utils.time_utils import TimeUtils

logger = logging.getLogger("LarkToolset")


class LarkToolset:
    """Unified Lark/Feishu skill入口：IM、Drive、Calendar/Task 共用单一 client."""

    def __init__(self, app_id: str, app_secret: str, user_open_id: str = None, image_save_dir: str = "/app/data/images"):
        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()

        self.user_open_id = user_open_id
        self.image_save_dir = image_save_dir
        os.makedirs(self.image_save_dir, exist_ok=True)

        self.calendar_id: Optional[str] = None
        self.tasklist_guid: Optional[str] = None

    # -------------------- IM --------------------
    def send_text_message(self, receive_id: str, text: str, receive_id_type: str = "chat_id") -> ToolResponse:
        try:
            content = json.dumps({"text": text}, ensure_ascii=False)
            body = CreateMessageRequestBody.builder() \
                .receive_id(receive_id) \
                .msg_type("text") \
                .content(content) \
                .build()

            req = CreateMessageRequest.builder() \
                .receive_id_type(receive_id_type) \
                .request_body(body) \
                .build()

            resp = self.client.im.v1.message.create(req)
            if not resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 发送失败: {resp.msg} (code {resp.code})")])
            return ToolResponse(content=[TextBlock(type="text", text="✅ 消息已发送")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 异常: {e}")])

    def download_message_image(self, message_id: str, image_key: str) -> ToolResponse:
        try:
            req = GetMessageResourceRequest.builder() \
                .message_id(message_id) \
                .file_key(image_key) \
                .type("image") \
                .build()

            resp = self.client.im.v1.message_resource.get(req)
            if not resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 下载失败: {resp.msg}")])

            file_name = f"{message_id}_{image_key}.jpg"
            file_path = os.path.join(self.image_save_dir, file_name)
            with open(file_path, "wb") as f:
                f.write(resp.file.read())

            return ToolResponse(content=[
                TextBlock(type="text", text=f"✅ 图片已就绪: {file_path}"),
                {
                    "type": "image",
                    "source": {
                        "type": "url",
                        "url": file_path
                    }
                }
            ])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 异常: {e}")])

    # -------------------- Drive --------------------
    def upload_file(self, local_path: str, parent_folder_token: str) -> ToolResponse:
        if not os.path.exists(local_path):
            return ToolResponse(content=[TextBlock(type="text", text="❌ 本地文件不存在")])
        try:
            file_name = os.path.basename(local_path)
            file_size = os.path.getsize(local_path)
            with open(local_path, "rb") as f:
                body = UploadAllFileRequestBody.builder() \
                    .file_name(file_name) \
                    .parent_type("explorer") \
                    .parent_node(parent_folder_token) \
                    .size(file_size) \
                    .file(f) \
                    .build()

                req = UploadAllFileRequest.builder().request_body(body).build()
                resp = self.client.drive.v1.file.upload_all(req)

            if not resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 上传失败: {resp.msg}")])
            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 上传成功: {file_name}\n🔗 Token: {resp.data.file_token}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 上传异常: {e}")])

    def read_file_base64(self, file_token: str) -> ToolResponse:
        try:
            req = DownloadFileRequest.builder().file_token(file_token).build()
            resp = self.client.drive.v1.file.download(req)
            if not resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 下载失败: {resp.msg}")])

            data = resp.file.read()
            b64 = base64.b64encode(data).decode("utf-8")
            return ToolResponse(content=[TextBlock(type="text", text=b64)])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 读取异常: {e}")])

    def list_folder_files(self, folder_token: str) -> ToolResponse:
        try:
            req = ListFileRequest.builder() \
                .folder_token(folder_token) \
                .page_size(50) \
                .build()
            resp = self.client.drive.v1.file.list(req)
            if not resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 获取列表失败: {resp.msg}")])

            files = resp.data.files or []
            if not files:
                return ToolResponse(content=[TextBlock(type="text", text="📂 该文件夹为空。")])

            lines = []
            for f in files:
                icon = "📁" if f.type == "folder" else "📄"
                lines.append(f"- {icon} {f.name} (Token: {f.token})")
            return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 列表异常: {e}")])

    def extract_token_from_url(self, url: str) -> ToolResponse:
        token = ""
        if "/file/" in url:
            token = url.split("/file/")[1].split("/")[0].split("?")[0]
        elif "/folder/" in url:
            token = url.split("/folder/")[1].split("/")[0].split("?")[0]
        return ToolResponse(content=[TextBlock(type="text", text=token or "⚠️ 未提取到 token")])

    # -------------------- Tasks & Calendar --------------------
    def _ensure_tasklist(self) -> str:
        if self.tasklist_guid:
            return self.tasklist_guid
        target_name = "🤖 Agent 协作清单"
        try:
            req = lark.api.task.v2.ListTasklistRequest.builder() \
                .page_size(50) \
                .build()
            resp = self.client.task.v2.tasklist.list(req)
            if resp.success() and resp.data.items:
                for tl in resp.data.items:
                    if tl.name == target_name:
                        self.tasklist_guid = tl.guid
                        break
            if not self.tasklist_guid:
                members = []
                if self.user_open_id:
                    members.append(lark.api.task.v2.Member.builder()
                                   .id(self.user_open_id)
                                   .type("user")
                                   .role("editor")
                                   .build())
                body = lark.api.task.v2.InputTasklist.builder() \
                    .name(target_name) \
                    .members(members) \
                    .build()
                create_req = lark.api.task.v2.CreateTasklistRequest.builder() \
                    .user_id_type("open_id") \
                    .request_body(body) \
                    .build()
                create_resp = self.client.task.v2.tasklist.create(create_req)
                if create_resp.success():
                    self.tasklist_guid = create_resp.data.tasklist.guid
            return self.tasklist_guid or ""
        except Exception as e:
            logger.error(f"Init tasklist failed: {e}")
            return ""

    def _ensure_calendar(self) -> str:
        if self.calendar_id:
            return self.calendar_id
        try:
            req = lark.api.calendar.v4.ListCalendarRequest.builder().build()
            resp = self.client.calendar.v4.calendar.list(req)
            if resp.success() and resp.data.calendar_list:
                for cal in resp.data.calendar_list:
                    if cal.summary in ["Agent协作日历", "Agent公共日历"]:
                        self.calendar_id = cal.calendar_id
                        break
            if not self.calendar_id:
                body = lark.api.calendar.v4.Calendar.builder() \
                    .summary("Agent公共日历") \
                    .permissions("public") \
                    .color(16711680) \
                    .build()
                create_req = lark.api.calendar.v4.CreateCalendarRequest.builder() \
                    .request_body(body).build()
                create_resp = self.client.calendar.v4.calendar.create(create_req)
                if create_resp.success():
                    self.calendar_id = create_resp.data.calendar.calendar_id
            return self.calendar_id or ""
        except Exception as e:
            logger.error(f"Init calendar failed: {e}")
            return ""

    def create_task(self, summary: str, due_time: str = None, members: List[str] = None) -> ToolResponse:
        if not self._ensure_tasklist():
            return ToolResponse(content=[TextBlock(type="text", text="❌ 未找到协作清单")])
        try:
            body_builder = lark.api.task.v2.InputTask.builder().summary(summary)
            if due_time:
                ts_ms = TimeUtils.to_ms_timestamp(due_time)
                if ts_ms:
                    body_builder.due(lark.api.task.v2.Due.builder().timestamp(ts_ms).is_all_day(False).build())
            member_objs = []
            if self.user_open_id:
                member_objs.append(lark.api.task.v2.Member.builder()
                                  .id(self.user_open_id)
                                  .type("user")
                                  .role("assignee")
                                  .build())
            if members:
                for uid in members:
                    if uid == self.user_open_id:
                        continue
                    member_objs.append(lark.api.task.v2.Member.builder()
                                      .id(uid)
                                      .type("user")
                                      .role("follower")
                                      .build())
            if member_objs:
                body_builder.members(member_objs)
            body_builder.tasklists([
                lark.api.task.v2.TaskInTasklistInfo.builder().tasklist_guid(self.tasklist_guid).build()
            ])
            req = lark.api.task.v2.CreateTaskRequest.builder() \
                .user_id_type("open_id") \
                .request_body(body_builder.build()) \
                .build()
            resp = self.client.task.v2.task.create(req)
            if not resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 任务创建失败: {resp.msg}")])
            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 任务已创建: {summary}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 异常: {e}")])

    def list_tasks(self, show_completed: bool = False) -> ToolResponse:
        if not self._ensure_tasklist():
            return ToolResponse(content=[TextBlock(type="text", text="❌ 未找到协作清单")])
        try:
            req_builder = lark.api.task.v2.TasksTasklistRequest.builder() \
                .tasklist_guid(self.tasklist_guid) \
                .user_id_type("open_id") \
                .page_size(50)
            if not show_completed:
                req_builder.completed(False)
            req = req_builder.build()
            resp = self.client.task.v2.tasklist.tasks(req)
            if not resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 查询清单失败: {resp.msg}")])
            items = resp.data.items or []
            if not items:
                return ToolResponse(content=[TextBlock(type="text", text="📭 清单暂无任务")])
            tz_cn = datetime.timezone(datetime.timedelta(hours=8))
            lines = []
            for item in items:
                is_done = (item.completed_at is not None) and (item.completed_at != "0")
                status_icon = "✅" if is_done else "🔲"
                time_info = ""
                if is_done:
                    try:
                        ts = int(item.completed_at) / 1000
                        dt = datetime.datetime.fromtimestamp(ts, tz_cn)
                        time_info = f"完成于 {dt.strftime('%m-%d %H:%M')}"
                    except Exception:
                        time_info = "已完成"
                elif item.due:
                    try:
                        ts = int(item.due.timestamp) / 1000
                        dt = datetime.datetime.fromtimestamp(ts, tz_cn)
                        time_info = f"截止 {dt.strftime('%m-%d %H:%M')}"
                    except Exception:
                        time_info = "无截止"
                else:
                    time_info = "无截止"
                lines.append(f"🆔 {item.guid} | {status_icon} {item.summary} ({time_info})")
            title = "📋 协作清单全览" if show_completed else "📋 待办事项"
            return ToolResponse(content=[TextBlock(type="text", text=f"{title}:\n" + "\n".join(lines))])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 系统异常: {e}")])

    def delete_task(self, task_guid: str) -> ToolResponse:
        try:
            req = lark.api.task.v2.DeleteTaskRequest.builder().task_guid(task_guid).build()
            resp = self.client.task.v2.task.delete(req)
            if not resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 删除失败: {resp.msg}")])
            return ToolResponse(content=[TextBlock(type="text", text="✅ 任务已删除")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 删除失败: {e}")])

    def create_calendar_event(self, summary: str, start_time: str, end_time: str,
                              description: str = "", location: str = "", attendees: List[str] = None) -> ToolResponse:
        if not self._ensure_calendar():
            return ToolResponse(content=[TextBlock(type="text", text="❌ 未找到日历")])
        ts_start_sec = TimeUtils.to_sec_timestamp(start_time)
        ts_end_sec = TimeUtils.to_sec_timestamp(end_time)
        if not ts_start_sec or not ts_end_sec:
            return ToolResponse(content=[TextBlock(type="text", text="❌ 时间格式错误")])
        try:
            event_body = lark.api.calendar.v4.CalendarEvent.builder() \
                .summary(summary) \
                .description(description) \
                .start_time(lark.api.calendar.v4.TimeInfo.builder().timestamp(ts_start_sec).build()) \
                .end_time(lark.api.calendar.v4.TimeInfo.builder().timestamp(ts_end_sec).build()) \
                .location(location) \
                .build()

            if attendees:
                attendee_objs = [lark.api.calendar.v4.EventAttendee.builder()
                                 .member_id(a).member_type("user").build() for a in attendees]
                event_body.attendees(attendee_objs)

            req = lark.api.calendar.v4.CreateCalendarEventRequest.builder() \
                .calendar_id(self.calendar_id) \
                .request_body(event_body) \
                .build()
            resp = self.client.calendar.v4.calendar_event.create(req)
            if not resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 日程创建失败: {resp.msg}")])
            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 已创建日程: {summary}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 异常: {e}")])

    def list_calendar_events(self, start_time: str = None, end_time: str = None) -> ToolResponse:
        if not self._ensure_calendar():
            return ToolResponse(content=[TextBlock(type="text", text="❌ 未找到日历")])
        # 默认查看今天到明天
        if not start_time:
            start_time = datetime.datetime.now().strftime("%Y-%m-%d 00:00:00")
        if not end_time:
            end_time = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
        ts_start = TimeUtils.to_sec_timestamp(start_time)
        ts_end = TimeUtils.to_sec_timestamp(end_time)
        if not ts_start or not ts_end:
            return ToolResponse(content=[TextBlock(type="text", text="❌ 时间格式错误")])
        try:
            req = lark.api.calendar.v4.ListCalendarEventRequest.builder() \
                .calendar_id(self.calendar_id) \
                .time_min(ts_start) \
                .time_max(ts_end) \
                .build()
            resp = self.client.calendar.v4.calendar_event.list(req)
            if not resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 查询失败: {resp.msg}")])
            events = resp.data.items or []
            if not events:
                return ToolResponse(content=[TextBlock(type="text", text="📭 时间段内无日程")])
            tz_cn = datetime.timezone(datetime.timedelta(hours=8))
            lines = []
            for ev in events:
                try:
                    st = datetime.datetime.fromtimestamp(int(ev.start_time.timestamp), tz_cn).strftime("%m-%d %H:%M")
                    et = datetime.datetime.fromtimestamp(int(ev.end_time.timestamp), tz_cn).strftime("%m-%d %H:%M")
                except Exception:
                    st = ev.start_time.timestamp
                    et = ev.end_time.timestamp
                lines.append(f"- {ev.summary} ({st} - {et})")
            return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 异常: {e}")])
