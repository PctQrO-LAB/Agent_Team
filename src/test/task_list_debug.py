import os
import time
import lark_oapi as lark
from lark_oapi.api.task.v2 import *

from src.test.test_lark_schedule import SCHEDULER_APP_ID


def main():
    print("🚀 开始测试：环境变量 + 读写双向验证 (SDK修正版)...")

    # ================= 1. 从环境变量获取配置 =================
    APP_ID = os.environ.get("SCHEDULER_APP_ID")
    APP_SECRET = os.environ.get("SCHEDULER_APP_SECRET")
    USER_OPEN_ID = os.environ.get("USER_OPEN_ID")

    # 简单检查
    if not all([APP_ID, APP_SECRET, USER_OPEN_ID]):
        print("❌ 错误: 缺少环境变量 (LARK_APP_ID, LARK_APP_SECRET, LARK_USER_OPEN_ID)")
        return

    client = lark.Client.builder() \
        .app_id(APP_ID) \
        .app_secret(APP_SECRET) \
        .log_level(lark.LogLevel.INFO) \
        .build()

    # ================= 2. 创建清单 & 拉人 =================
    list_name = f"Agent_Test_{int(time.time())}"
    print(f"\n📋 [Step 1] 创建清单: '{list_name}'...")

    # 构造请求
    member = Member.builder().id(USER_OPEN_ID).type("user").role("editor").build()
    input_list = InputTasklist.builder().name(list_name).members([member]).build()
    req_list = CreateTasklistRequest.builder().user_id_type("open_id").request_body(input_list).build()

    resp_list = client.task.v2.tasklist.create(req_list)
    if not resp_list.success():
        print(f"❌ 创建清单失败: {resp_list.msg}")
        return

    list_guid = resp_list.data.tasklist.guid
    print(f"✅ 清单创建成功 GUID: {list_guid}")

    # ================= 3. 在清单中创建任务 =================
    task_summary = "🤖 Agent 自检任务"
    print(f"\n📝 [Step 2] 创建任务: '{task_summary}'...")

    assignee = Member.builder().id(USER_OPEN_ID).type("user").role("assignee").build()
    in_list_info = TaskInTasklistInfo.builder().tasklist_guid(list_guid).build()

    input_task = InputTask.builder() \
        .summary(task_summary) \
        .members([assignee]) \
        .tasklists([in_list_info]) \
        .build()

    req_task = CreateTaskRequest.builder().user_id_type("open_id").request_body(input_task).build()

    resp_task = client.task.v2.task.create(req_task)
    if not resp_task.success():
        print(f"❌ 创建任务失败: {resp_task.msg}")
        return

    created_task_guid = resp_task.data.task.guid
    print(f"✅ 任务创建成功 Task GUID: {created_task_guid}")

    # ================= 4. Agent 尝试读取任务 (已修正) =================
    print(f"\n👀 [Step 3] Agent 正在尝试读取清单内容...")

    # ✅ 使用官方文档提供的正确类名: TasksTasklistRequest
    req_read = TasksTasklistRequest.builder() \
        .tasklist_guid(list_guid) \
        .user_id_type("open_id") \
        .page_size(50) \
        .build()

    try:
        # ✅ 使用官方文档提供的正确方法: client.task.v2.tasklist.tasks
        resp_read = client.task.v2.tasklist.tasks(req_read)

    except Exception as e:
        print(f"❌ SDK 调用读取接口出错: {e}")
        return

    if not resp_read.success():
        print(f"❌ 读取失败: {resp_read.code} - {resp_read.msg}")
        return

    # 遍历打印找到的任务
    tasks = resp_read.data.items or []
    found = False
    print(f"🔎 在该清单中发现了 {len(tasks)} 个任务:")

    for t in tasks:
        print(f"   - GUID: {t.guid} | 标题: {t.summary}")
        if t.guid == created_task_guid:
            found = True

    if found:
        print("\n🎉🎉🎉 验证通过！Agent 成功读取到了它创建的任务！")
    else:
        print("\n⚠️ 列表读取成功，但未找到目标任务 (可能API有延迟，请去飞书APP确认)")


if __name__ == "__main__":
    main()