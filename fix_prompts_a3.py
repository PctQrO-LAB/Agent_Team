with open('src/config/prompts.py', 'r', encoding='utf-8') as f:
    text = f.read()

concept_add = """
## 4. 特别工作流 (Important Workflow)
你生成概念图后，务必要明确【文本世界观】和【物理美术资产】的边界：
- 第一步：使用 `save_scene` 保存**场景的世界观和文本设定**到场景表。**注意：场景表仅用于存储文本设定，不包含物理图片路径。**
- 第二步：使用 `generate_image` 生成物理概念图（传入正确的绝对路径参数）。**这将会生成实际的图片文件。**
- 第三步：将生成的概念图记录为「场景设计资产」，也就是环境(en)。**必须**使用 `save_design_asset` (category='en') 进行记录！这非常重要，后续设计只能通过设计资产表查询到具体的物理概念图路径。
"""

design_add = """
## 4. 特别工作流 (Important Workflow)
- **严格遵循**：在读取别人的场景概念图时，你**必须**调用 `get_design_asset` 或 `query_design_assets` 并指定 `category='en'` 来查找！**绝对不要使用 `get_scene` 查找图片路径，场景表仅包含文本世界观设定。** 当产生属于你自己的新资源时，一定要用 `save_design_asset` 等登记！
"""

text = text.replace(
    "- **表达克制**：沟通时不“互吹”，用最简洁的方式说明问题。", 
    "- **表达克制**：沟通时不“互吹”，用最简洁的方式说明问题。\n" + concept_add
)

text = text.replace(
    "- **表达克制**：一切以解决问题和推进设计为核心。", 
    "- **表达克制**：一切以解决问题和推进设计为核心。\n" + design_add
)

with open('src/config/prompts.py', 'w', encoding='utf-8') as f:
    f.write(text)

