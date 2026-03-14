import os
import re

agent_files = [
    "assistant_agent.py",
    "casting_agent.py",
    "concept_agent.py",
    "design_agent.py",
    "qc_agent.py",
    "schedule_agent.py",
    "storyboard_agent.py"
]

for filename in agent_files:
    filepath = os.path.join("src", "agents", filename)
    with open(filepath, "r") as f:
        content = f.read()

    # Move `self.plan_notebook = plan_notebook` AFTER `super().__init__(...)`
    # Let's just remove it from before super().__init__ and put it after
    if "self.plan_notebook = plan_notebook" in content:
        content = content.replace("        self.plan_notebook = plan_notebook\n", "")
        # Now find the end of super().__init__(...) call.
        # It usually ends with `)` on a line with `        )`
        # Let's replace `        )` with `        )\n        self.plan_notebook = plan_notebook`
        # But wait, there might be multiple `)` in the file.
        # Let's replace `max_iters=15,\n        )` or `plan_notebook=plan_notebook,\n        )`
        content = re.sub(r'(plan_notebook=plan_notebook[^\)]*\))', r'\1\n        self.plan_notebook = plan_notebook', content, count=1)
        
    with open(filepath, "w") as f:
        f.write(content)
print("Fixed.")
