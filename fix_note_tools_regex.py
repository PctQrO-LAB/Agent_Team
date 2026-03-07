import re

with open('src/tools/note_tools.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove image_path from save_scene def
content = re.sub(
    r'(def save_scene\([^{]+?)(\s*image_path:\s*str\s*=\s*None,)([^)]+\):)',
    r'\1\3',
    content,
    flags=re.MULTILINE
)

# Remove concept_v logic in save_scene
content = re.sub(
    r'\s*# 自动生成预设 Concept 路径\s*effective_version = version or 1\s*if not image_path:\s*#.*?\s*#.*?\s*image_path = f"\{project\}/\{scene\}/_Concept/concept_v\{effective_version\}\.jpg"\n',
    '\n',
    content,
    flags=re.DOTALL
)

# Replace insert query in save_scene
content = re.sub(
    r'(sql = \'\'\'INSERT INTO scenes \([^,]+, [^,]+, [^,]+, [^,]+, [^,]+, [^,]+, [^,]+, [^,]+)(, image_path)(, version\).*?)(VALUES \([^,]+, [^,]+, [^,]+, [^,]+, [^,]+, [^,]+, [^,]+, [^,]+)(, \?)(, \?\)\'\'\')',
    r'\1\3\n                         \4\6',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'(\s*\(project, scene, world_prompt, elements, mood, color_tone, lighting_mood,\s*characters), image_path, version\)\)',
    r'\1, version))',
    content,
    flags=re.MULTILINE
)

with open('src/tools/note_tools.py', 'w', encoding='utf-8') as f:
    f.write(content)

