import re

with open('src/tools/note_tools.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace(
    "                   characters: str = None,\n                   image_path: str = None,\n                   version: int = None",
    "                   characters: str = None,\n                   version: int = None"
)

text = text.replace(
    "if image_path: fields.append(\"image_path=?\"); params.append(image_path)",
    ""
)

old_insert = """                sql = '''INSERT INTO scenes (project, scene, world_prompt, elements, mood, color_tone, lighting_mood, 
                                          characters, image_path, version)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
                self._execute_with_retry(self.shared_conn, sql,
                                         (project, scene, world_prompt, elements, mood, color_tone, lighting_mood,
                                          characters, image_path, version))"""

new_insert = """                sql = '''INSERT INTO scenes (project, scene, world_prompt, elements, mood, color_tone, lighting_mood, 
                                          characters, version)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'''
                self._execute_with_retry(self.shared_conn, sql,
                                         (project, scene, world_prompt, elements, mood, color_tone, lighting_mood,
                                          characters, version))"""
                                          
text = text.replace(old_insert, new_insert)

with open('src/tools/note_tools.py', 'w', encoding='utf-8') as f:
    f.write(text)

