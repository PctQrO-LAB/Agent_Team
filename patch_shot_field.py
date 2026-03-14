with open('src/tools/generate_tools.py', 'r') as f:
    content = f.read()

content = content.replace("SELECT * FROM shots WHERE project = ? AND uid = ?", "SELECT * FROM shots WHERE project = ? AND scene = ?")

with open('src/tools/generate_tools.py', 'w') as f:
    f.write(content)
