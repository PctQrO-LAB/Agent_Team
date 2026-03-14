---
name: film_notebook
description: 管理影视项目、场景、镜头和设计资产的技能
---

# 笔记本影视技能

## 作用
- 建立与维护影视项目结构（项目/场景/镜头/资产）
- 记录与读取设计资产、镜头、场景设定
- 读写相关文件/图片

## 依赖工具函数
- AgentNotebook: save_project, save_scene, save_shot, save_shot_batch, save_design_asset, get_project, get_scene, get_shot, get_design_asset, save_beat, save_beat_list, get_beat_list
- FileTool: init_workspace, read_image_as_url

## 使用说明
1) 初始化结构：调用 init_workspace(asset_id) 建立文件夹并入库兜底结构。
2) 保存前先询问项目/场景/镜头/资产标识及版本信息。
3) 读取时给出可用条目的摘要（名称、版本、路径）。
4) 如需生成图片与落盘，请交由外部工作流（n8n 等）；本地仅保留读取 URL 的能力。

## 输出格式示例
- "读取设计资产：名称/版本/路径列表"

## 注意事项
- 路径以相对项目根目录描述，避免暴露绝对路径给外部用户。
- 不要覆盖同名文件，建议提示用户确认或生成新版本号。

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
- 物理图片资产使用 `save_design_asset` (提供 asset_id，如 p01-sc01-en01) 即可自动保存，不再需要手写绝对路径。
- 当你需要查找已经生成的场景概念图时，**必须**使用 `query_design_assets(project, category='en')`，或者直接 `get_design_asset(project, category='en', uid='pXX-scXX-enXX')`！

### ⚠️ 数据库表结构及查询规范 (极其重要，严禁编造列名和表名！)
系统中的主要表格有 `scenes`（存场景描述）, `design_assets`（存角色、道具、概念图等物理资产）, `shots`（存分镜）。
**请注意：系统中根本不存在 `characters` 这个表！获取角色信息请查询 `design_assets`表，条件为 `category='ch'`。**
在调用任何查询工具（如 `query_note`、`read_note`）时，各个表中的具体“个体编号”列名已经全部统一为 `uid`。
1. **查具体个体信息时，过滤条件永远使用 `uid` 列**：
   - 查某个指定场景(`scenes`表): `{"uid": "p01-sc01"}`
   - 查某个指定设计图或角色(`design_assets`表): `{"uid": "p01-sc01-en01"}` 或 `{"uid": "p01-ch01"}`
   - 查某个指定分镜(`shots`表): `{"uid": "p01-sc01-sh01"}`
2. **需要批量列出时，可以使用 `project` 或 `scene` 作为分类过滤标签**：
   - 查项目 p01 的所有场景: `{"project": "p01"}`
   - 查场景 p01-sc01 下的所有数据: `{"scene": "p01-sc01"}` (此条件针对含有该层级信息的表格如shots)
   - 查所有的角色或某一类资产: 表名填 `design_assets`，过滤条件 `{"category": "ch"}`
