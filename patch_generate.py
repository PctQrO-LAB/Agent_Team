with open('src/tools/generate_tools.py', 'r') as f:
    content = f.read()

content = content.replace("WHERE project = ? AND category = ? AND name = ?", "WHERE project = ? AND category = ? AND uid = ?")
content = content.replace("(project, category, name, describe, image_path, version)", "(project, category, uid, describe, image_path, version)")
content = content.replace("WHERE project = ? AND scene = ?", "WHERE project = ? AND uid = ?")
content = content.replace("WHERE name = ?", "WHERE uid = ?")
content = content.replace("scene_row['file_path']", "scene_row['uid']") # Hmm scenes don't have file_path anymore?

with open('src/tools/generate_tools.py', 'w') as f:
    f.write(content)
