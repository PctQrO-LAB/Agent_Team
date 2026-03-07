import re

with open('src/tools/note_tools.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace(
    "f\"🖼️ Concept Image: {data.get('image_path') or 'N/A'}\\n\"",
    ""
)

with open('src/tools/note_tools.py', 'w', encoding='utf-8') as f:
    f.write(text)

