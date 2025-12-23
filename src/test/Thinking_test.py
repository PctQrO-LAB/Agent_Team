import sys
import os
import json
from pydantic import BaseModel, Field  # 👈 需要用到 Pydantic

# 路径黑魔法
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))


from src.tools.google_task_tools import add_calendar_event, get_calendar_events
from src.agentscope.tool import Toolkit  # 导入 Toolkit


# === 1. 定义思考模型 (Pydantic) ===
class ThinkingModel(BaseModel):
    """
    这是一个"外挂大脑"。
    我们强制模型在填 summary 和 time 之前，必须先填 thinking。
    """
    thinking: str = Field(
        description="【强制】在做出排程决定前，请先在此处进行思考。\n"
                    "你需要分析：任务的预估耗时、选定该时间段的理由、以及是否避开了用餐时间。",
    )


# === 2. 注册并扩展 ===
def setup_toolkit():
    toolkit = Toolkit()

    # 先注册原版函数
    toolkit.register_tool_function(add_calendar_event)
    toolkit.register_tool_function(get_calendar_events)

    # 🔥 核心动作：注入思考模型
    # 这会把 ThinkingModel 里的字段合并到 add_calendar_event 的 Schema 里
    toolkit.set_extended_model("add_calendar_event", ThinkingModel)

    return toolkit


# === 3. 验证效果 ===
def main():
    toolkit = setup_toolkit()
    schemas = toolkit.get_json_schemas()

    print("🚀 注入成功！来看看 DeepSeek 看到的加强版指令：")
    print("=" * 50)

    # 找到 add_calendar_event 打印出来
    for schema in schemas:
        if schema['function']['name'] == 'add_calendar_event':
            print(json.dumps(schema, indent=2, ensure_ascii=False))

            # 检查 thinking 是否真的进去了
            props = schema['function']['parameters']['properties']
            if "thinking" in props:
                print("\n✅ 成功检测到 'thinking' 字段！")
                print(f"📝 描述: {props['thinking']['description']}")

    print("=" * 50)


if __name__ == "__main__":
    main()