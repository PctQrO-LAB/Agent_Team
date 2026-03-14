with open('src/tools/note_tools.py', 'r') as f:
    content = f.read()

# For design_assets: project=? AND category=? AND name=? -> ... uid=?
content = content.replace("cursor.execute('SELECT id, version FROM design_assets WHERE project=? AND category=? AND name=?'", "cursor.execute('SELECT id, version FROM design_assets WHERE project=? AND category=? AND uid=?'")
content = content.replace("_generate_next_id(self.shared_conn, 'design_assets', 'name', prefix_str)", "_generate_next_id(self.shared_conn, 'design_assets', 'uid', prefix_str)")
content = content.replace("INSERT INTO design_assets (project, category, name,", "INSERT INTO design_assets (project, category, uid,")


# For shot: 
content = content.replace("cursor.execute('SELECT id, version FROM shots WHERE project=? AND scene=? AND shot=?'", "cursor.execute('SELECT id, version FROM shots WHERE project=? AND scene=? AND uid=?'")
content = content.replace("_generate_next_id(self.shared_conn, 'shots', 'shot', prefix_str)", "_generate_next_id(self.shared_conn, 'shots', 'uid', prefix_str)")
content = content.replace("INSERT INTO shots (project, scene, shot", "INSERT INTO shots (project, scene, uid")


with open('src/tools/note_tools.py', 'w') as f:
    f.write(content)
