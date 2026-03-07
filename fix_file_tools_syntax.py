import re

with open('src/tools/file_tools.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Fix unterminated string
text = re.sub(r'text=f"✅ 场景场地已就绪。.*?\{concept_path\}"\)\]\)', 
              r'text=f"✅ 场景场地已就绪。\\n📂 场景根目录: {path}\\n💡 【强调】请务必将该场景的概念图(Concept)生成至此专属路径: {concept_path}")])', 
              text, flags=re.DOTALL)

with open('src/tools/file_tools.py', 'w', encoding='utf-8') as f:
    f.write(text)
