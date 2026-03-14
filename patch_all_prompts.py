import re

with open("src/config/prompts.py", "r") as f:
    content = f.read()

# 1. Add plan strategy to all defined prompts
plan_str = """
## 💡 计划能力 (Plan & Subtasks)
你现在已经装备了 `PlanNotebook`。当遇到复杂或多步任务时：
1. 先调用 `create_plan` 拆解任务，列出阶段性的里程碑和子任务。
2. 每当你完成一个子任务，或委托其他 Agent 执行时，调用 `update_plan_status` 及时更新任务状态。
3. 把任务规划当成你的本能，避免一次性执行太多步骤而混乱。
"""
prompts = [
    "SCHEDULE_SYSTEM_PROMPT",
    "DESIGN_SYSTEM_PROMPT",
    "CONCEPT_SYSTEM_PROMPT",
    "STORYBOARD_SYSTEM_PROMPT",
    "ASSISTANT_SYSTEM_PROMPT",
    "QC_SYSTEM_PROMPT",
    "PRODUCER_SYSTEM_PROMPT"
]
for p in prompts:
    pattern = rf'({p} = """[\s\S]*?)"""'
    content = re.sub(pattern, lambda m: m.group(1) + plan_str + '"""', content)

# 2. Add broadcast to Producer
broadcast_str = """
- **广播通知机制 (Broadcast Capability)**：
  - 当你需要向所有其他智能体（如所有参与项目的 Agent）同步重要的阶段性进展、统一的审核标准调整、或者紧急的进度叫停时，请使用 `broadcast_message` 工具进行广播，而不需要逐一私聊。
"""
# Find a place to insert in PRODUCER_SYSTEM_PROMPT. "4. 计划与决策思路" or similar.
# Let's just append it before the new plan_str in PRODUCER
content = content.replace("## 💡 计划能力 (Plan & Subtasks)", broadcast_str + "\n## 💡 计划能力 (Plan & Subtasks)", 1)

with open("src/config/prompts.py", "w") as f:
    f.write(content)

print("Done patching.")
