import json
import os
import lark_oapi as lark
from lark_oapi.api.calendar.v4 import *
from dotenv import load_dotenv

# 加载环境变量
SCHEDULER_APP_ID="cli_a9c4a9ed8fb9dcd6"
SCHEDULER_APP_SECRET="2p0HZVZiJHWhaR8qIGnjFf7ZkAlFrMsx"

USER_OPEN_ID="ou_28d9e5ce34a5d520e676f045614ca38c"


def claim_calendar_ownership():
    # 1. 从 .env 获取配置
    app_id = SCHEDULER_APP_ID
    app_secret = SCHEDULER_APP_SECRET
    user_open_id = USER_OPEN_ID

    if not all([app_id, app_secret, user_open_id]):
        print("❌ 错误：请检查 .env 文件，确保 SCHEDULER_APP_ID, SCHEDULER_APP_SECRET, USER_OPEN_ID 都已填写！")
        return

    print(f"🚀 正在启动提权程序...")
    print(f"   - App ID: {app_id}")
    print(f"   - 目标用户: {user_open_id}")

    # 2. 创建客户端
    client = lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .log_level(lark.LogLevel.INFO) \
        .build()

    # 3. 第一步：找到那个公共日历的 ID
    print("\n🔍 正在搜索 'Agent协作日历'...")
    list_req = ListCalendarRequest.builder().build()
    list_resp = client.calendar.v4.calendar.list(list_req)

    target_cal_id = ""
    if list_resp.success() and list_resp.data.calendar_list:
        for cal in list_resp.data.calendar_list:
            # 这里的名字要和你之前创建的一致
            if cal.summary == "Agent协作日历":
                target_cal_id = cal.calendar_id
                print(f"✅ 找到目标日历: {cal.summary}")
                print(f"   - ID: {target_cal_id}")
                print(f"   - 当前权限: {cal.role}")  # 机器人看这个日历的视角
                break

    if not target_cal_id:
        print("❌ 未找到 'Agent协作日历'，请先运行之前的测试脚本创建日历！")
        return

    # 4. 第二步：暴力提权 (Set Role to OWNER)
    print(f"\n⚡ 正在将用户 {user_open_id} 提升为管理员 (Owner)...")

    # 构造请求对象 (完全参考你提供的官方代码，只是把 role 改成了 owner)
    request = CreateCalendarAclRequest.builder() \
        .calendar_id(target_cal_id) \
        .user_id_type("open_id") \
        .request_body(CalendarAcl.builder()
                      .role("owner")  # 👈 关键修改：这里改成了 owner
                      .scope(AclScope.builder()
                             .type("user")
                             .user_id(user_open_id)
                             .build())
                      .build()) \
        .build()

    # 发起请求
    response = client.calendar.v4.calendar_acl.create(request)

    # 5. 处理结果
    if not response.success():
        # 如果报错 105002，说明已经是 Owner 了，或者已经是成员需要用 Update 接口
        # 但 Create 接口通常能覆盖权限，我们先看报错
        print(f"❌ 提权失败!")
        print(f"   - Code: {response.code}")
        print(f"   - Msg: {response.msg}")
        return

    print("🎉 提权成功！")
    print("   - 你现在是该日历的【管理员/所有者】了。")
    print("   - 你拥有最高权限：可编辑、可删除、可管理成员。")


if __name__ == "__main__":
    claim_calendar_ownership()