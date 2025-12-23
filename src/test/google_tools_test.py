# src/test/google_tools_test.py
import os
import sys
import warnings

# === 1. 第一步：强行屏蔽红字警告 (必须放在最最前面) ===
# 只要是废弃警告，统统不显示
warnings.filterwarnings("ignore", category=DeprecationWarning)

# === 2. 第二步：强行设置代理 (关键救命药) ===
# 这里假设你的代理端口是 7890 (ClashX 默认)
# 如果你的端口不一样，请修改这里的数字
print("🌐 正在初始化网络代理 (127.0.0.1:7890)...")
os.environ["http_proxy"] = "http://127.0.0.1:7890"
os.environ["https_proxy"] = "http://127.0.0.1:7890"
os.environ["ALL_PROXY"] = "socks5://127.0.0.1:7890"

# === 3. 搞定路径，确保能导入 src 下的代码 ===
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(project_root)

# === 4. 导入工具 ===
try:
    from src.tools.google_task_tools import (
        add_calendar_event,
        add_google_task,
        get_calendar_events,
        get_google_tasks
    )
except ImportError as e:
    print(f"❌ 导入失败，请检查路径: {e}")
    sys.exit(1)

import datetime


def run_test():
    print("🚀 开始进行纯工具测试 (不经过 Agent)...\n")

    # 动态生成一个“明天上午10点”的时间
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    test_date_str = tomorrow.strftime("%Y-%m-%d")
    start_time = f"{test_date_str} 10:00"
    end_time = f"{test_date_str} 11:00"

    # ==========================================
    # 测试 1: 创建日历 (Calendar)
    # ==========================================
    print(f"👉 [测试 1] 正在尝试创建日历: {start_time}")
    print("   (如果这里卡住超过10秒，说明代理没配置对，或者 Google 连不上)")

    try:
        res_cal = add_calendar_event(
            summary="【工具测试】手动触发日历",
            start_time=start_time,
            end_time=end_time
        )
        print(f"   ✅ 结果: {res_cal}\n")
    except Exception as e:
        print(f"   ❌ 失败: {e}\n")

    # ==========================================
    # 测试 2: 创建待办 (Tasks)
    # ==========================================
    print(f"👉 [测试 2] 正在尝试创建 Tasks: {start_time}")
    try:
        res_task = add_google_task(
            title="【工具测试】手动触发待办",
            due_time=start_time
        )
        print(f"   ✅ 结果: {res_task}\n")
    except Exception as e:
        print(f"   ❌ 失败: {e}\n")

    # ==========================================
    # 测试 3: 读取验证 (Read)
    # ==========================================
    print("👉 [测试 3] 正在读取日历...")
    try:
        events = get_calendar_events(limit=5)
        print(events)
    except Exception as e:
        print(f"   ❌ 读取失败: {e}")


if __name__ == "__main__":
    run_test()