import re

with open('src/config/prompts.py', 'r', encoding='utf-8') as f:
    text = f.read()

rule_snippet = """3. **全局唯一资产编号规范 (Global Unique Asset ID System)**：
   - 必须使用绝对编号作为 name（项目、场景、资产命名均如此），绝对禁止使用中文或自然语言拼音/单词。
   - 格式规范：`pXX-scXX-类别XX`。如项目: `p01`；场景: `p01-sc01`；角色: `p01-ch01`；场景概念: `p01-sc01-en01`
   - 查询和修改数据库或相关工具时，如果不确定，直接留空(None)或只打前缀让底层自动发号，并仔细阅读返回的最新ID！"""

text = text.replace("2. 存储时必须确立场次号与镜头号，文件名必须规范。", 
                    "2. 存储时必须确立场次号与镜头号，文件名必须规范。\n" + rule_snippet)

with open('src/config/prompts.py', 'w', encoding='utf-8') as f:
    f.write(text)
