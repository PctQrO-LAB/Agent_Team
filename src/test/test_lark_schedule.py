import sys
import os
import time
SCHEDULER_APP_ID = "cli_a9c4a9ed8fb9dcd6"
SCHEDULER_APP_SECRET = "2p0HZVZiJHWhaR8qIGnjFf7ZkAlFrMsx"

# --------------------------------------------------------
# 路径修复 (确保能找到 src)
# --------------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(project_root)

from dotenv import load_dotenv
from src.tools.lark_tools import LarkTool

load_dotenv()


def get_text(response):
    """辅助函数：安全地提取返回内容中的文本"""
    # 如果是 ToolResponse 对象，尝试获取 content
    content_list = getattr(response, 'content', [])

    if not content_list:
        return "❌ 无返回内容"

    first_item = content_list[0]

    # 核心修复：同时支持 对象属性(.text) 和 字典键值(['text'])
    if isinstance(first_item, dict):
        return first_item.get("text", "无文本")
    else:
        return getattr(first_item, "text", "无文本")


def test_lark_lifecycle():
    app_id = SCHEDULER_APP_ID
    app_secret = SCHEDULER_APP_SECRET

    if not app_id:
        print("❌ 错误: 请配置 SCHEDULER_APP_ID")
        return

    print(f"🚀 初始化 LarkTool (AppID: {app_id}...)")
    tool = LarkTool(app_id, app_secret)

    # --- 1. 测试日程 (Calendar) ---
    print("\n[1/6] 正在查询现有日程...")
    res = tool.get_calendar_events()
    print(f"   >>> {get_text(res)}")  # 👈 使用修复后的函数

    print("\n[2/6] 正在创建测试日程 (1小时后)...")
    now_ts = time.time() + 3600
    start_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts))
    end_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts + 1800))

    res = tool.create_calendar_event(
        summary="[Agent测试] 自动创建的日程",
        start_time=start_str,
        end_time=end_str,
        description="这是一条测试数据，稍后会自动删除"
    )
    result_text = get_text(res)  # 👈 使用修复后的函数
    print(f"   >>> {result_text}")

    # 提取 ID
    #

    # --- 2. 测试任务 (Task) ---
    print("\n[4/6] 正在创建测试任务...")
    res = tool.create_task(summary="[Agent测试] 这是一个待办任务")
    result_text = get_text(res)  # 👈 使用修复后的函数
    print(f"   >>> {result_text}")

    new_task_id = None
    if "ID: " in result_text:
        try:
            new_task_id = result_text.split("ID: ")[1].split(")")[0].strip()
        except:
            pass

    print("\n[5/6] 正在查询任务列表...")
    res = tool.get_tasks()
    print(f"   >>> {get_text(res)}")  # 👈 使用修复后的函数



if __name__ == "__main__":
    test_lark_lifecycle()