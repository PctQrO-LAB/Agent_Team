import re

with open('src/tools/file_tools.py', 'r', encoding='utf-8') as f:
    code = f.read()

new_func = """    def init_scene_structure(self, project: str, scene: str) -> ToolResponse:
        \"\"\"[初始化] 创建场景目录 (含Concept区)，并记录路径到数据库。使用时必须以严格编号交互。\"\"\"
        
        # 强制格式化机制：如果传了 sc01，强制补齐为 p01-sc01
        import re
        if scene and not scene.startswith(project):
            # 将多余的杠去掉重组
            clean_scene = scene.lstrip('-')
            scene = f"{project}-{clean_scene}"
            
        try:
            path = self.manager.init_scene(project, scene)
            concept_path = f"{path}/_Concept"
            
            # --- Auto-Record to DB ---
            try:
                import os, sqlite3
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                db_path = os.path.join(base_dir, "data", "shared", "agent_shared.db")
                
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE scenes SET file_path = ? WHERE project = ? AND scene = ?", (path, project, scene))
                    if cursor.rowcount == 0:
                        cursor.execute("INSERT INTO scenes (project, scene, file_path) VALUES (?, ?, ?)", (project, scene, path))
                    conn.commit()
            except Exception as db_e:
                print(f"⚠️ Warning: Failed to record scene path to DB: {db_e}")

            return ToolResponse(content=[TextBlock(type="text", text=f"✅ 场景场地已就绪。\n📂 场景根目录: {path}\n💡 【强调】请务必将该场景的概念图(Concept)生成至此专属路径: {concept_path}")])
        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])"""

# Replace the specific method
code = re.sub(r'    def init_scene_structure\(self, project: str, scene: str\) -> ToolResponse:.*?(?=    def init_design_structure)', 
              new_func + "\n\n", code, flags=re.DOTALL)

with open('src/tools/file_tools.py', 'w', encoding='utf-8') as f:
    f.write(code)
