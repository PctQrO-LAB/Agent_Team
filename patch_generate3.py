with open('src/tools/generate_tools.py', 'r') as f:
    content = f.read()

content = content.replace("cursor.execute(\"SELECT file_path FROM scenes", "cursor.execute(\"SELECT id FROM scenes")
content = content.replace("scene_root_path = scene_row['uid']", "scene_root_path = f'/app/production/{project}/{project}-{scene}/Shots'")

with open('src/tools/generate_tools.py', 'w') as f:
    f.write(content)
