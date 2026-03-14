import re

with open("src/config/prompts.py", "r") as f:
    content = f.read()

# Define the string to append
plan_str = """
## 💡 计划能力 (Plan & Subtasks)
你现在已经装备了 `PlanNotebook`。当遇到复杂或多步任务时：
1. 先调用 `create_plan` 拆解任务，列出阶段性的里程碑和子任务。
2. 每当你完成一个子任务，或委托其他 Agent 执行时，调用 `update_plan_status` 及时更新任务状态。
3. 把任务规划当成你的本能，避免一次性执行太多步骤而混乱。
"""

# We want to append this to all prompts (SCHEDULE, DESIGN, CONCEPT, STORYBOARD, ASSISTANT, QC).
prompts = [
    "SCHEDULE_SYSTEM_PROMPT",
    "DESIGN_SYSTEM_PROMPT",
    "CONCEPT_SYSTEM_PROMPT",
    "STORYBOARD_SYSTEM_PROMPT",
    "ASSISTANT_SYSTEM_PROMPT",
    "QC_SYSTEM_PROMPT"
]

for p in prompts:
    # Find the end of the prompt block
    # It looks like: PROMPT_NAME = """ ... """
    # We will find PROMPT_NAME = """ and then the next """ and insert before it
    pattern = rf'({p} = """[\s\S]*?)"""'
    content = re.sub(pattern, lambda m: m.group(1) + plan_str + '"""', content)

with open("src/config/prompts.py", "w") as f:
    f.write(content)
print("Prompts patched.")
