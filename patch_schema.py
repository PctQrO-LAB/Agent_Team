import re

with open('src/tools/note_tools.py', 'r') as f:
    content = f.read()

# For scenes: project=? AND scene=? -> project=? AND uid=?
# Also self._generate_next_id(..., 'scenes', 'scene' -> 'uid')
content = content.replace("cursor.execute('SELECT id FROM scenes WHERE project=? AND scene=?', (project, scene))", "cursor.execute('SELECT id FROM scenes WHERE project=? AND uid=?', (project, scene))")
content = content.replace("scene = self._generate_next_id(self.shared_conn, 'scenes', 'scene', prefix_str)", "scene = self._generate_next_id(self.shared_conn, 'scenes', 'uid', prefix_str)")
content = content.replace("INSERT INTO scenes (project, scene, world_prompt", "INSERT INTO scenes (project, uid, world_prompt")

with open('src/tools/note_tools.py', 'w') as f:
    f.write(content)
