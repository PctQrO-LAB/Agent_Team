import os

rule = """
## 📌 全局唯一资产编号规范 (Global Unique Asset ID System)
在调用任何资产、场景、镜头相关的保存或读取工具时，必须遵循以下规则：
- 必须使用绝对编号作为名称（项目、场景、资产命名均如此），绝对禁止使用中文或自然语言拼音/单词。
- 格式规范：`pXX-scXX-类别XX`
- 项目(Project): `p01`
- 场景(Scene): `p01-sc01`
- 镜头(Shot): `p01-sc01-sh01`
- 角色(Character): `p01-ch01` (全局主角) 或 `p01-sc01-ch01` (场内辅助)
- 场景概念(Environment): `p01-sc01-en01`
- 道具(Prop): `p01-sc01-pr01`
- 如果不确定要创建的编号是多少，在调用保存工具时将其设为 None 或只提供前缀，交由后台自动分配并仔细记录返回的最终 ID。
"""

files_to_update = ['skills/film_notebook/SKILL.md', 'skills/file_tools/SKILL.md']

for filepath in files_to_update:
    if os.path.exists(filepath):
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(rule)
