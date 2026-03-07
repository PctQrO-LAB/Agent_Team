import re

with open('src/config/prompts.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Update ConceptAgent
text = text.replace(
    "- 第一步：使用 `save_scene` (或类似工具) 保存**场景的世界观和文本设定**到场景表。",
    "- 第一步：使用 `save_scene` 保存**场景的世界观和文本设定**到场景表。**注意：场景表仅用于存储文本设定，不包含物理图片路径。**"
)

text = text.replace(
    "- 第二步：使用 `generate_image` 生成物理概念图（传入正确的绝对路径参数）。",
    "- 第二步：使用 `generate_image` 生成物理概念图（传入正确的绝对路径参数）。**这将会生成实际的图片文件。**"
)

text = text.replace(
    "- 第三步：将生成的概念图记录为「场景设计资产」，必须使用 `save_design_asset` (category='en') 进行记录！这非常重要，后续设计才能查询到。",
    "- 第三步：将生成的概念图记录为「场景设计资产」，也就是环境(en)。**必须**使用 `save_design_asset` (category='en') 进行记录！这非常重要，后续设计只能通过设计资产表查询到具体的物理概念图路径。"
)


# Update DesignAgent
text = text.replace(
    "- 严格遵循：在读取别人的场景概念图时，你应当调用 `get_scene` 或是查资产表找到图片路径。当产生属于你自己的新资源时，一定要用 `save_design_asset` 等登记！",
    "- 严格遵循：在读取别人的场景概念图时，你**必须**调用 `get_design_asset` 或 `query_design_assets` 并指定 `category='en'` 来查找！**绝对不要使用 `get_scene` 查找图片路径，场景表仅包含文本世界观设定。** 当产生属于你自己的新资源时，一定要用 `save_design_asset` 等登记！"
)


with open('src/config/prompts.py', 'w', encoding='utf-8') as f:
    f.write(text)

