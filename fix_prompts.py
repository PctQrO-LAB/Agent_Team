import re

with open('src/config/prompts.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = """**全局唯一资产编号规范 (Global Unique Asset ID System)**：
   - 必须使用绝对编号作为 name（项目、场景、资产均如此），绝对禁止使用中文或自然语言拼音/单词。
   - 格式规范：`pXX-scXX-类别XX`
   - 项目(Project): `p01`, `p02`
   - 场景(Scene): `p01-sc01`, `p01-sc02`
   - 镜头(Shot): `p01-sc01-sh01`, `p01-sc01-sh02`
   - 角色(Character): `p01-ch01` (全局主角) 或 `p01-sc01-ch01` (场内群演)
   - 场景概念(Environment): `p01-sc01-en01`
   - 道具(Prop): `p01-sc01-pr01`
   - 任何涉及命名的参数必须严格采用此编号形式，如果不确定资产编号是什么，直接在调用工具时将其留空(None)或只提供前缀，交由后台系统自动发号，并仔细阅读系统返回的最终合法 ID 并记录在随后的交流中！"""

text = re.sub(r'\d+\.\s+\*\*命名严格极简.*?\n\s+- 正确示例：.*?\n\s+- 禁止示例：.*?\n', 
              lambda m: m.group(0).split('.')[0] + ". " + replacement + "\n", text, flags=re.MULTILINE)

with open('src/config/prompts.py', 'w', encoding='utf-8') as f:
    f.write(text)
