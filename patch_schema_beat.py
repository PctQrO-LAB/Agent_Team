with open('src/tools/note_tools.py', 'r') as f:
    content = f.read()

# For save_beat: 
content = content.replace("cursor.execute('SELECT id FROM beat_list WHERE project=? AND scene=? AND beat_num=?'", "cursor.execute('SELECT id FROM beat_list WHERE project=? AND scene=? AND uid=?'")
content = content.replace("INSERT INTO beat_list (project, scene, beat_num, description) VALUES", "INSERT INTO beat_list (project, scene, uid, description) VALUES")

with open('src/tools/note_tools.py', 'w') as f:
    f.write(content)
