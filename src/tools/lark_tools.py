import json
import os
import time
import datetime
import logging
import lark_oapi as lark
from typing import Optional, List, Dict, Any
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock

# 配置日志
logger = logging.getLogger("LarkTool")


class LarkTool:
    """
    飞书 (Lark/Feishu) 工具类，用于 Agent 与飞书日历和任务进行交互。

    支持功能：
    1. 自动化任务清单管理：自动创建专属协作清单，并将用户添加为协作者。
    2. 任务管理：在清单中创建任务、查询清单任务、删除任务。
    3. 日历管理：查询日程、创建日程、删除日程。
    """

    def __init__(self, app_id: str, app_secret: str, user_open_id: str = None):
        """
        初始化 LarkTool 实例。

        Args:
            app_id (str): 飞书应用的 App ID。
            app_secret (str): 飞书应用的 App Secret。
            user_open_id (str, optional): 默认协作用户的 Open ID。
                                          用于在创建清单时自动拉人，或创建任务时自动指派。
                                          如果未提供，部分协作功能可能受限。
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self.user_open_id = user_open_id

        # 初始化飞书客户端
        # log_level 设置为 INFO 以减少控制台噪音，调试时可改为 DEBUG
        self.client = lark.Client.builder() \
            .app_id(self.app_id) \
            .app_secret(self.app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()

        # 初始化资源 ID
        # 这些 ID 会在第一次调用相关功能时自动获取或创建
        self.calendar_id = self._init_calendar()
        self.tasklist_guid = self._init_tasklist()

    def _init_calendar(self) -> str:
        """
        初始化日历资源。

        逻辑：
        1. 尝试查找名为 "Agent公共日历" 或 "Agent协作日历" 的现有日历。
        2. 如果不存在，则创建一个新的 "Agent公共日历"。

        Returns:
            str: 目标日历的 calendar_id，如果失败则返回空字符串。
        """
        try:
            req = lark.api.calendar.v4.ListCalendarRequest.builder().build()
            resp = self.client.calendar.v4.calendar.list(req)
            if resp.success() and resp.data.calendar_list:
                for cal in resp.data.calendar_list:
                    if cal.summary in ["Agent协作日历", "Agent公共日历"]:
                        return cal.calendar_id

            # 创建新日历
            calendar_body = lark.api.calendar.v4.Calendar.builder() \
                .summary("Agent公共日历") \
                .permissions("public") \
                .color(16711680) \
                .build()
            create_req = lark.api.calendar.v4.CreateCalendarRequest.builder() \
                .request_body(calendar_body).build()
            create_resp = self.client.calendar.v4.calendar.create(create_req)
            return create_resp.data.calendar.calendar_id if create_resp.success() else ""
        except Exception as e:
            logger.error(f"Failed to init calendar: {e}")
            return ""

    def _init_tasklist(self) -> str:
        """
        初始化任务清单资源。
        """
        target_name = "🤖 Agent 协作清单"
        guid = ""

        try:
            # 1. 遍历寻找现有清单
            # ❌ 错误写法: .limit(50)
            # ✅ 正确写法: .page_size(50)
            req = lark.api.task.v2.ListTasklistRequest.builder() \
                .page_size(50) \
                .build()

            resp = self.client.task.v2.tasklist.list(req)

            if resp.success() and resp.data.items:
                for tl in resp.data.items:
                    if tl.name == target_name:
                        guid = tl.guid
                        break

            # 2. 如果没找到，创建新的（原子操作：创建同时拉人）
            if not guid:
                members = []
                if self.user_open_id:
                    members.append(lark.api.task.v2.Member.builder()
                                   .id(self.user_open_id)
                                   .type("user")
                                   .role("editor")
                                   .build())

                input_list = lark.api.task.v2.InputTasklist.builder() \
                    .name(target_name) \
                    .members(members) \
                    .build()

                create_req = lark.api.task.v2.CreateTasklistRequest.builder() \
                    .user_id_type("open_id") \
                    .request_body(input_list) \
                    .build()

                create_resp = self.client.task.v2.tasklist.create(create_req)
                if create_resp.success():
                    guid = create_resp.data.tasklist.guid
                    logger.info(f"Created new tasklist: {guid}")
                else:
                    logger.error(f"Failed to create tasklist: {create_resp.msg}")

            # 3. 补救措施：如果清单已存在但用户可能不在里面
            elif guid and self.user_open_id:
                self._add_user_to_tasklist(guid, self.user_open_id)

            return guid
        except Exception as e:
            logger.error(f"Init tasklist failed: {e}")
            return ""

    def _add_user_to_tasklist(self, tasklist_guid: str, user_id: str):
        """
        辅助方法：将指定用户添加为清单的可编辑成员。
        """
        try:
            member = lark.api.task.v2.Member.builder().id(user_id).type("user").role("editor").build()
            body = lark.api.task.v2.AddMembersTasklistRequestBody.builder().members([member]).build()
            req = lark.api.task.v2.AddMembersTasklistRequest.builder() \
                .tasklist_guid(tasklist_guid) \
                .user_id_type("open_id") \
                .request_body(body) \
                .build()
            self.client.task.v2.tasklist.add_members(req)
        except Exception as e:
            # 用户可能已经在清单里了，忽略报错
            logger.debug(f"Add member warning (safe to ignore): {e}")

    def _parse_time_str(self, time_str: str) -> Optional[str]:
        """
        将自然语言时间或 ISO 时间字符串转换为【毫秒级】时间戳字符串。

        飞书 Task V2 API 要求时间戳为毫秒 (ms)，而 Python 默认是秒。
        """
        if not time_str: return None
        try:
            dt = None
            # 1. 尝试 ISO 格式解析 (例如: '2025-12-30T12:00:00')
            if "T" in time_str:
                dt = datetime.datetime.fromisoformat(time_str)
            # 2. 尝试常规日期格式解析 (例如: '2025-12-30 12:00:00')
            else:
                dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")

            # 3. 强制转换为北京时间 (UTC+8)
            tz_cn = datetime.timezone(datetime.timedelta(hours=8))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz_cn)

            # 4. 关键修正：转换为毫秒级时间戳 (乘以1000)
            timestamp_ms = int(dt.timestamp() * 1000)
            return str(timestamp_ms)

        except ValueError:
            logger.warning(f"Time parse failed for: {time_str}")
            return None

    # =================================================
    # ✅ 任务操作 (核心功能)
    # =================================================

    def create_task(self, summary: str, due_time: str = None, extra_member_ids: List[str] = None) -> ToolResponse:
        """
        在【Agent 协作清单】中创建一个新任务。

        功能：
        1. 自动归档到协作清单。
        2. 设置你自己为【负责人】(Assignee)。
        3. 如果提供了 extra_member_ids，将其设置为【关注人】(Follower)。
        4. 正确设置截止时间 (毫秒级时间戳)。

        Args:
            summary (str): 任务标题/摘要。
            due_time (str, optional): 截止时间 (格式：yyyy-MM-dd HH:mm:ss 或 ISO)。
            extra_member_ids (List[str], optional): 其他参与者/关注人的 Open ID 列表。

        Returns:
            ToolResponse: 包含创建结果的文本响应。
        """
        # 0. 确保清单 ID 已初始化
        if not self.tasklist_guid:
            self.tasklist_guid = self._init_tasklist()
            if not self.tasklist_guid:
                return ToolResponse(content=[TextBlock(type="text", text="❌ 错误: 无法初始化协作清单，无法创建任务。")])

        try:
            # 1. 构造任务基本信息
            body_builder = lark.api.task.v2.InputTask.builder().summary(summary)

            # 2. ✅ 修复截止时间 (使用毫秒级时间戳)
            if due_time:
                ts_ms = self._parse_time_str(due_time)
                if ts_ms:
                    # 飞书 API 要求：传入 timestamp 字符串，且必须是毫秒
                    body_builder.due(lark.api.task.v2.Due.builder()
                                     .timestamp(ts_ms)
                                     .is_all_day(False)  # 默认为具体时间点，非全天
                                     .build())

            # 3. ✅ 修复成员逻辑 (负责人 + 关注人)
            members = []

            # 3.1 必须：把你设为【负责人】(Assignee)
            if self.user_open_id:
                members.append(lark.api.task.v2.Member.builder()
                               .id(self.user_open_id)
                               .type("user")
                               .role("assignee")  # 关键：角色是 assignee
                               .build())

            # 3.2 可选：把其他人设为【关注人】(Follower)
            if extra_member_ids:
                for uid in extra_member_ids:
                    # 避免重复添加自己
                    if uid == self.user_open_id: continue

                    members.append(lark.api.task.v2.Member.builder()
                                   .id(uid)
                                   .type("user")
                                   .role("follower")  # 关键：其他人通常设为关注人，避免权限冲突
                                   .build())

            if members:
                body_builder.members(members)

            # 4. 关键逻辑：直接指定所属清单
            task_in_list = lark.api.task.v2.TaskInTasklistInfo.builder() \
                .tasklist_guid(self.tasklist_guid).build()
            body_builder.tasklists([task_in_list])

            # 5. 发起请求
            req = lark.api.task.v2.CreateTaskRequest.builder() \
                .user_id_type("open_id") \
                .request_body(body_builder.build()) \
                .build()

            resp = self.client.task.v2.task.create(req)

            if not resp.success():
                return ToolResponse(
                    content=[TextBlock(type="text", text=f"❌ 任务创建失败: {resp.msg} (Code: {resp.code})")])

            # 6. 成功返回
            return ToolResponse(content=[
                TextBlock(type="text", text=f"✅ 任务已创建: {summary}\n⏰ 截止: {due_time if due_time else '无'}")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 系统异常: {str(e)}")])

    def get_tasks(self, show_completed: bool = False) -> ToolResponse:
        """
        获取协作清单中的任务列表。

        逻辑说明：
        根据官方文档，任务的完成状态由 `completed_at` 字段决定。
        - completed_at == "0": 未完成
        - completed_at != "0": 已完成 (值为完成时的毫秒级时间戳)

        Args:
            show_completed (bool): 是否包含已完成的任务。
                                   False (默认): 仅返回未完成任务 (TODO)。
                                   True: 返回所有任务 (TODO + DONE)。
        """
        if not self.tasklist_guid:
            self.tasklist_guid = self._init_tasklist()  # 尝试重新初始化
            if not self.tasklist_guid:
                return ToolResponse(content=[TextBlock(type="text", text="❌ 未找到协作清单")])

        try:
            # 1. 构造请求
            # 根据文档，completed 参数控制过滤：
            # - true: 只看已完成
            # - false: 只看未完成
            # - 不填: 查看所有
            req_builder = lark.api.task.v2.TasksTasklistRequest.builder() \
                .tasklist_guid(self.tasklist_guid) \
                .user_id_type("open_id") \
                .page_size(50)  # 默认每页50条

            if not show_completed:
                req_builder.completed(False)  # 默认模式：只看未完成
            # 如果 show_completed=True，则不设置 completed 参数，即拉取所有状态

            req = req_builder.build()

            # 2. 调用接口获取列表
            resp = self.client.task.v2.tasklist.tasks(req)

            if not resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 查询清单失败: {resp.msg}")])

            tasks = resp.data.items or []
            if not tasks:
                return ToolResponse(content=[TextBlock(type="text", text="📭 协作清单目前没有任务。")])

            res = []
            tz_cn = datetime.timezone(datetime.timedelta(hours=8))

            for item in tasks:
                # 3. 解析状态 (核心修改)
                # 文档明确：completed_at 为 "0" 表示未完成，否则为毫秒时间戳
                is_done = (item.completed_at is not None) and (item.completed_at != "0")

                # 4. 解析时间显示
                time_info = ""

                # 情况A: 已完成 -> 显示完成时间
                if is_done:
                    status_icon = "✅"
                    try:
                        # 解析完成时间 (毫秒 -> 秒)
                        ts = int(item.completed_at) / 1000
                        dt = datetime.datetime.fromtimestamp(ts, tz_cn)
                        time_info = f"完成于 {dt.strftime('%m-%d %H:%M')}"
                    except:
                        time_info = "已完成"

                # 情况B: 未完成 -> 显示截止时间
                else:
                    status_icon = "🔲"
                    if item.due:
                        try:
                            # 解析截止时间 (毫秒 -> 秒)
                            ts = int(item.due.timestamp) / 1000
                            dt = datetime.datetime.fromtimestamp(ts, tz_cn)
                            time_info = f"截止 {dt.strftime('%m-%d %H:%M')}"
                        except:
                            time_info = "无截止时间"
                    else:
                        time_info = "无截止"

                # 5. 组装输出
                # 格式: 🔲 任务标题 (截止 12-30 18:00) [ID: xxx]
                res.append(f"{status_icon} **{item.summary}** ({time_info}) `ID:{item.guid}`")

            title = "📋 **协作清单全览**" if show_completed else "📋 **待办事项**"
            return ToolResponse(content=[TextBlock(type="text", text=f"{title}:\n" + "\n".join(res))])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 系统异常: {str(e)}")])

    def delete_task(self, task_guid: str) -> ToolResponse:
        """
        根据任务 GUID 删除任务。

        Args:
            task_guid (str): 任务的全局唯一 ID。
        """
        try:
            req = lark.api.task.v2.DeleteTaskRequest.builder().task_guid(task_guid).build()
            self.client.task.v2.task.delete(req)
            return ToolResponse(content=[TextBlock(type="text", text="✅ 任务已删除")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 删除失败: {e}")])

    def inspect_task_list(self, task_guids: List[str]) -> ToolResponse:
        """
        批量查询指定 ID 的任务状态。

        Args:
            task_guids (List[str]): 任务 GUID 列表。
        """
        if not task_guids: return ToolResponse(content=[TextBlock(type="text", text="❓ 未提供任务ID")])
        results = []
        for guid in task_guids:
            try:
                req = lark.api.task.v2.GetTaskRequest.builder() \
                    .task_guid(guid).user_id_type("open_id").build()
                resp = self.client.task.v2.task.get(req)
                if not resp.success(): continue

                t = resp.data.task
                status = "✅ DONE" if t.completed_at else "🔲 TODO"
                results.append(f"{status} {t.summary}")
            except:
                pass
        return ToolResponse(content=[TextBlock(type="text", text="\n".join(results))])

    # =================================================
    # 📅 日历操作 (标准功能)
    # =================================================

    def create_calendar_event(self, summary: str, start_time: str, end_time: str,
                              description: str = "", location: str = "",
                              attendee_ids: List[str] = None) -> ToolResponse:
        """
        创建一个新的日历日程，并自动添加参与人。
        """
        if not self.calendar_id:
            self.calendar_id = self._init_calendar()
            if not self.calendar_id:
                return ToolResponse(content=[TextBlock(type="text", text="❌ 错误: 未找到日历 ID，无法创建日程。")])

        # 1. 获取毫秒级时间戳 (由 _parse_time_str 返回)
        ts_start_ms = self._parse_time_str(start_time)
        ts_end_ms = self._parse_time_str(end_time)

        if not ts_start_ms or not ts_end_ms:
            return ToolResponse(content=[TextBlock(type="text", text="❌ 时间格式错误")])

        # 2. 关键修正：转换为【秒级】时间戳 (Calendar API 要求)
        # 如果长度大于 10 位，说明是毫秒，需要 / 1000
        ts_start_sec = str(int(ts_start_ms) // 1000)
        ts_end_sec = str(int(ts_end_ms) // 1000)

        try:
            # ==========================================
            # 第一步：创建基础日程
            # ==========================================
            event_body = lark.api.calendar.v4.CalendarEvent.builder() \
                .summary(summary) \
                .description(description) \
                .start_time(lark.api.calendar.v4.TimeInfo.builder()
                            .timestamp(ts_start_sec)  # 使用秒级
                            .timezone("Asia/Shanghai")  # 显式指定时区
                            .build()) \
                .end_time(lark.api.calendar.v4.TimeInfo.builder()
                          .timestamp(ts_end_sec)  # 使用秒级
                          .timezone("Asia/Shanghai")
                          .build()) \
                .need_notification(True) \
                .color(1) \
                .build()

            if location:
                event_body.location = lark.api.calendar.v4.EventLocation.builder().name(location).build()

            create_req = lark.api.calendar.v4.CreateCalendarEventRequest.builder() \
                .calendar_id(self.calendar_id) \
                .request_body(event_body) \
                .build()

            create_resp = self.client.calendar.v4.calendar_event.create(create_req)

            if not create_resp.success():
                return ToolResponse(content=[TextBlock(type="text", text=f"❌ 日程创建失败: {create_resp.msg}")])

            event_id = create_resp.data.event.event_id

            # ==========================================
            # 第二步：添加参与人 (你 + 其他人)
            # ==========================================
            attendees_to_add = []

            # 1. 添加你自己 (必选，否则日程不会出现在你的视图里)
            if self.user_open_id:
                attendees_to_add.append(
                    lark.api.calendar.v4.CalendarEventAttendee.builder()
                    .type("user")
                    .user_id(self.user_open_id)
                    .is_optional(False)
                    .build()
                )

            # 2. 添加其他人
            if attendee_ids:
                for uid in attendee_ids:
                    if uid == self.user_open_id: continue
                    attendees_to_add.append(
                        lark.api.calendar.v4.CalendarEventAttendee.builder()
                        .type("user")
                        .user_id(uid)
                        .is_optional(False)
                        .build()
                    )

            attendee_msg = ""
            if attendees_to_add:
                add_attendees_body = lark.api.calendar.v4.CreateCalendarEventAttendeeRequestBody.builder() \
                    .attendees(attendees_to_add) \
                    .build()

                add_attendees_req = lark.api.calendar.v4.CreateCalendarEventAttendeeRequest.builder() \
                    .calendar_id(self.calendar_id) \
                    .event_id(event_id) \
                    .user_id_type("open_id") \
                    .request_body(add_attendees_body) \
                    .build()

                attendee_resp = self.client.calendar.v4.calendar_event_attendee.create(add_attendees_req)

                if attendee_resp.success():
                    attendee_msg = "(已邀请参与人)"
                else:
                    attendee_msg = f"(⚠️ 邀请人失败: {attendee_resp.msg})"

            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 日程已创建: {summary} {attendee_msg}")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ 系统异常: {str(e)}")])

    def get_calendar_events(self, time_min: str = None, time_max: str = None) -> ToolResponse:
        """
        查询未来一周或指定时间段的日程。
        """
        if not self.calendar_id:
            return ToolResponse(content=[TextBlock(type="text", text="Error: No Calendar")])

        ts_min = self._parse_time_str(time_min) or self._parse_time_str(
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ts_max = self._parse_time_str(time_max) or str(int(time.time()) + 7 * 86400)

        req = lark.api.calendar.v4.ListCalendarEventRequest.builder() \
            .calendar_id(self.calendar_id) \
            .start_time(ts_min) \
            .end_time(ts_max) \
            .build()

        resp = self.client.calendar.v4.calendar_event.list(req)
        res = [f"🆔 {e.event_id} | 📝 {e.summary}" for e in resp.data.items or []]
        return ToolResponse(content=[TextBlock(type="text", text="\n".join(res) if res else "无日程")])

    def delete_calendar_event(self, event_id: str) -> ToolResponse:
        """删除指定日程。"""
        req = lark.api.calendar.v4.DeleteCalendarEventRequest.builder() \
            .calendar_id(self.calendar_id).event_id(event_id).build()
        self.client.calendar.v4.calendar_event.delete(req)
        return ToolResponse(content=[TextBlock(type="text", text="✅ 日程已删除")])

    def debug_user_identity(self) -> ToolResponse:
        """调试用：返回当前配置的用户 ID 和清单 GUID。"""
        return ToolResponse(
            content=[TextBlock(type="text", text=f"User ID: {self.user_open_id}, List GUID: {self.tasklist_guid}")])