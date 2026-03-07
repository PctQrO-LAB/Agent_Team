import glob

files = glob.glob('skills/*/SKILL.md')

for filepath in files:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Update note_tools descriptions
    if "save_scene" in content:
        content = content.replace(
            "- `image_path`: **[可选]** （如果有预生成图片或者资产图路径）",
            ""
        )
        content = content.replace(
            "   - `image_path` (str, optional): The relative path to the concept image.",
            ""
        )
        content = content.replace(
            "保存或更新一个场景（Scene）的世界观、设定及图文状态。",
            "保存或更新一个场景（Scene）的世界观、设定。注意：场景表仅用于存储文本设定，不包含物理图片路径，物理图片路径必须使用save_design_asset单独登记为'en'分类的环境资产！"
        )
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

