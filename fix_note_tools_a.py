import re

with open('src/tools/note_tools.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace save_scene entirely to avoid regex issues
old_code = """
    def save_scene(self, project: str, scene: str = None,
                   world_prompt: str = None,
                   elements: str = None,
                   mood: str = None,
                   color_tone: str = None,
                   lighting_mood: str = None,
                   characters: str = None,
                   image_path: str = None,
                   version: int = None) -> ToolResponse:
        
        # 1. 自动派发符合规范的编号 p01-sc01
        import re
        prefix_str = f"{project}-sc"
        if not scene or not re.match(rf"^{prefix_str}\d+$", scene):
            scene = self._generate_next_id(self.shared_conn, 'scenes', 'scene', prefix_str)

        try:
            cursor = self.shared_conn.cursor()
            cursor.execute('SELECT id FROM scenes WHERE project=? AND scene=?', (project, scene))
            row = cursor.fetchone()

            if row:
                fields = []
                params = []
                if world_prompt: fields.append("world_prompt=?"); params.append(world_prompt)
                if elements: fields.append("elements=?"); params.append(elements)
                if mood: fields.append("mood=?"); params.append(mood)
                if color_tone: fields.append("color_tone=?"); params.append(color_tone)
                if lighting_mood: fields.append("lighting_mood=?"); params.append(lighting_mood)
                if characters: fields.append("characters=?"); params.append(characters)
                if image_path: fields.append("image_path=?"); params.append(image_path)
                if version is not None: fields.append("version=?"); params.append(version)
                
                if not fields:
                    return ToolResponse(content=[TextBlock(type="text", text="⚠️ 场景表未发生变更 (未传入有效字段)")])

                fields.append("updated_at=CURRENT_TIMESTAMP")
                sql = f"UPDATE scenes SET {', '.join(fields)} WHERE id=?"
                params.append(row[0])
                self._execute_with_retry(self.shared_conn, sql, tuple(params))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 场景已更新: {scene}")])

            else:
                # 自动生成预设 Concept 路径
                effective_version = version or 1
                if not image_path:
                     # 预设路径规则: project/scene/_Concept/concept_v{version}.jpg
                     # 注意：这里存的是相对路径或预期路径，实际文件可能还没生成
                     image_path = f"{project}/{scene}/_Concept/concept_v{effective_version}.jpg"
                
                sql = '''INSERT INTO scenes (project, scene, world_prompt, elements, mood, color_tone, lighting_mood, 
                                          characters, image_path, version)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
                self._execute_with_retry(self.shared_conn, sql,
                                         (project, scene, world_prompt, elements, mood, color_tone, lighting_mood,
                                          characters, image_path, version))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 新场景已创建: {scene}")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])
"""

new_code = """
    def save_scene(self, project: str, scene: str = None,
                   world_prompt: str = None,
                   elements: str = None,
                   mood: str = None,
                   color_tone: str = None,
                   lighting_mood: str = None,
                   characters: str = None,
                   version: int = None) -> ToolResponse:
        
        # 1. 自动派发符合规范的编号 p01-sc01
        import re
        prefix_str = f"{project}-sc"
        if not scene or not re.match(rf"^{prefix_str}\d+$", scene):
            scene = self._generate_next_id(self.shared_conn, 'scenes', 'scene', prefix_str)

        try:
            cursor = self.shared_conn.cursor()
            cursor.execute('SELECT id FROM scenes WHERE project=? AND scene=?', (project, scene))
            row = cursor.fetchone()

            if row:
                fields = []
                params = []
                if world_prompt: fields.append("world_prompt=?"); params.append(world_prompt)
                if elements: fields.append("elements=?"); params.append(elements)
                if mood: fields.append("mood=?"); params.append(mood)
                if color_tone: fields.append("color_tone=?"); params.append(color_tone)
                if lighting_mood: fields.append("lighting_mood=?"); params.append(lighting_mood)
                if characters: fields.append("characters=?"); params.append(characters)
                if version is not None: fields.append("version=?"); params.append(version)
                
                if not fields:
                    return ToolResponse(content=[TextBlock(type="text", text="⚠️ 场景表未发生变更 (未传入有效字段)")])

                fields.append("updated_at=CURRENT_TIMESTAMP")
                sql = f"UPDATE scenes SET {', '.join(fields)} WHERE id=?"
                params.append(row[0])
                self._execute_with_retry(self.shared_conn, sql, tuple(params))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 场景已更新: {scene}")])

            else:
                sql = '''INSERT INTO scenes (project, scene, world_prompt, elements, mood, color_tone, lighting_mood, 
                                          characters, version)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'''
                self._execute_with_retry(self.shared_conn, sql,
                                         (project, scene, world_prompt, elements, mood, color_tone, lighting_mood,
                                          characters, version))
                return ToolResponse(content=[TextBlock(type="text", text=f"✅ 新场景文本设定已创建: {scene}")])

        except Exception as e:
            return ToolResponse(content=[TextBlock(type="text", text=f"❌ Error: {e}")])
"""

if old_code in content:
    content = content.replace(old_code, new_code)
else:
    print("Warning: old_code not found in content exactly!")

# Update get_scene content
old_get_scene_info = """
                    f"🧑 Characters: {data.get('characters') or 'Not defined'}\n"
                    f"🖼️ Concept Image: {data.get('image_path') or 'N/A'}\n"
                    f"🧾 Version: {('v' + str(data.get('version'))) if data.get('version') else 'unknown'}"
"""
new_get_scene_info = """
                    f"🧑 Characters: {data.get('characters') or 'Not defined'}\n"
                    f"🧾 Version: {('v' + str(data.get('version'))) if data.get('version') else 'unknown'}"
"""

if old_get_scene_info in content:
    content = content.replace(old_get_scene_info, new_get_scene_info)

with open('src/tools/note_tools.py', 'w', encoding='utf-8') as f:
    f.write(content)

