with open('src/tools/note_tools.py', 'r') as f:
    content = f.read()

# Try to find missing ones like get_scene
content = content.replace("query += ' AND scene=?'", "query += ' AND uid=?'")
content = content.replace("WHERE project=? AND scene=?", "WHERE project=? AND uid=?")
# query_note mapping
content = content.replace("mapping = {'name': 'name',", "mapping = {'name': 'uid',")

with open('src/tools/note_tools.py', 'w') as f:
    f.write(content)
