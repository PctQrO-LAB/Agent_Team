import re

with open('src/config/prompts.py', 'r', encoding='utf-8') as f:
    text = f.read()

rule_snippet = """9. **全局唯一资产编号规范 (Global Unique Asset ID System)**：
   - 必须使用绝对编号作为名字或参数（项目、场景、资产命名均如此），禁止使用中文或自然语言。
   - 格式规范：`pXX-scXX-类别XX`。如项目: `p01`；场景: `p01-sc01`；角色: `p01-ch01`；场景概念: `p01-sc01-en01`
   - 查询和修改数据库或相关工具时，必须要使用严格的绝对编号。"""

# Find the Non-Negotiables block in Producer
text = text.replace("8. **审核前必须强制读取对应场次的剧本（文档）内容，进行图文一致性比对。未读取剧本（read_document_content）禁止给出任何审核结论。**", 
                    "8. **审核前必须强制读取对应场次的剧本（文档）内容，进行图文一致性比对。未读取剧本（read_document_content）禁止给出任何审核结论。**\n" + rule_snippet)

with open('src/config/prompts.py', 'w', encoding='utf-8') as f:
    f.write(text)
