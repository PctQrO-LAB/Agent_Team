import json
import sys
import os

# 1. 路径黑魔法 (确保能导入 src)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# 2. 导入 Toolkit 类
from agentscope.tool import Toolkit

# 3. 导入你的工具函数
from src.tools.google_task_tools import (
    get_calendar_events,
    add_calendar_event,
    delete_calendar_event,
    add_google_task,
    get_google_tasks,
    delete_google_task,
)


def main():
    print("🚀 开始注册工具箱...\n")

    # === 第一步：实例化 Toolkit ===
    toolkit = Toolkit()

    # === 第二步：注册工具 (Register) ===
    tools_to_register = [
        get_calendar_events,
        add_calendar_event,
        delete_calendar_event,
        add_google_task,
        get_google_tasks,
        delete_google_task,
    ]

    for tool_func in tools_to_register:
        toolkit.register_tool_function(tool_func)
        print(f"✅ 已注册: {tool_func.__name__}")

    # === 第三步：验证成果 (Verify) ===
    schemas = toolkit.get_json_schemas()  # 注意：有些版本可能是这个方法名，或者 toolkit.tools_instruction

    print(f"\n🎉 成功生成了 {len(schemas)} 个工具指令！")
    # 打印出来看看，检查你的 Docstring 是否被完美转换
    # json.dumps 会让格式变漂亮
    print(json.dumps(schemas, indent=2, ensure_ascii=False))
    print("=" * 50)

    # === 第四步：深度检查 (Deep Check) ===
    print("\n🕵️‍♂️ 深度体检 [add_calendar_event]:")

    found = False
    for schema in schemas:
        # 🔥 关键修正：先进入 'function' 层级
        if 'function' not in schema: continue  # 防御性编程

        func_info = schema['function']

        if func_info['name'] == 'add_calendar_event':
            found = True

            # 1. 检查描述
            desc = func_info.get('description', '')
            # 打印出来看看，防止为空
            print(f"  📝 描述预览: {desc[:30]}...")

            if "原子化" in desc or "双重" in desc:
                print("  ✅ 描述解析成功：检测到关键词")
            else:
                print("  ❌ 警告：描述似乎没解析对？请检查 Docstring")

            # 2. 检查参数
            # 参数在 function -> parameters -> properties
            params = func_info.get('parameters', {})
            props = params.get('properties', {})

            # 检查 start_time
            if 'start_time' in props:
                st_desc = props['start_time'].get('description', '')
                print(f"  ✅ 参数 start_time 已识别")
            else:
                print(f"  ❌ 漏掉了 start_time 参数")

            # 检查 reminder_minutes (int)
            if 'reminder_minutes' in props:
                rm_type = props['reminder_minutes'].get('type')
                if rm_type == 'integer':
                    print("  ✅ 参数 reminder_minutes: 类型正确 (integer)")
                else:
                    print(f"  ❌ 警告：reminder_minutes 类型是 {rm_type}，应为 integer")
            else:
                print("  ❌ 漏掉了 reminder_minutes 参数")

            # 3. 检查必填项
            required = params.get('required', [])
            print(f"  ✅ 必填参数列表: {required}")

            if 'summary' in required and 'start_time' in required:
                print("     (逻辑正确：标题和时间是必须的)")
            else:
                print("     ❌ 警告：必填项缺失！")

            if 'end_time' not in required:
                print("     (逻辑正确：结束时间是可选的)")
            else:
                print("     ❌ 警告：结束时间被错误的设为了必填！")

    if not found:
        print("❌ 严重错误：在生成的 Schema 里没找到 add_calendar_event！")


if __name__ == "__main__":
    main()