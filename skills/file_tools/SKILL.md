---
name: file_tools
description: 本地文件与目录初始化、存档与读取链接的技能
---

# 文件工具技能

## 作用
- 初始化项目/场景/设计/镜头目录结构
- 将本地图片转换为可访问 URL（若同步可用）

## 依赖工具函数
- FileTool: init_project_structure, init_scene_structure, init_design_structure, init_shot_structure, read_image_as_url

## 使用说明
1) 先确认项目/场景/镜头/资产名称与版本，再调用对应 init_* 以创建目录。
2) 读取图片 URL 仅在同步可用时返回；否则提示用户同步或检查路径。

## 输出格式示例
- "已创建设计目录: /app/production/<project>/_Design/<category>/<name>"
- "图片链接: https://..."

## 注意事项
- 路径使用相对项目的语义描述，避免暴露不必要的绝对路径。
- 避免覆盖已有文件；如可能覆盖需询问用户或生成新版本号。

## 📌 全局唯一资产编号规范 (Global Unique Asset ID System)
在调用任何资产、场景、镜头相关的保存或读取工具时，必须遵循以下规则：
- 必须使用绝对编号作为名称（项目、场景、资产命名均如此），绝对禁止使用中文或自然语言拼音/单词。
- 格式规范：`pXX-scXX-类别XX`
- 项目(Project): `p01`
- 场景(Scene): `p01-sc01`
- 镜头(Shot): `p01-sc01-sh01`
- 角色(Character): `p01-ch01` (全局主角) 或 `p01-sc01-ch01` (场内辅助)
- 场景概念(Environment): `p01-sc01-en01`
- 道具(Prop): `p01-sc01-pr01`
- 如果不确定要创建的编号是多少，在调用保存工具时将其设为 None 或只提供前缀，交由后台自动分配并仔细记录返回的最终 ID。


## 📌 特别工作流 (Important Workflow)
在保存概念图和读取时：
你需要知道文本设定和物理美术资产是分离的：
- `save_scene` 和 `get_scene` **只负责**保存和检索场景的世界观和文本设定。它们没有物理图片路径，不能存图或找图！
- 物理图片资产（尤其是大场景概念图）必须使用 `save_design_asset` 保存，并且将 `category` 设为 `'en'` (环境)。
- 当你需要查找已经生成的场景概念图时，**必须**使用 `query_design_assets(project, category='en')`，或者直接 `get_design_asset(project, category='en', name='pXX-scXX-enXX')`！
