---
name: generate_tools
description: 通过 n8n Webhook 委托生成图片/触发工作流
---

# 生成委托技能

## 作用
- 将 prompt 与目标路径发送到 n8n Webhook，触发生图或后续处理。

## 依赖工具函数
- GenerationTool: generate_image, generate_storyboard_batch

## 使用说明
### A. 单图/设计图生成 (generate_image)
1) 确认环境已配置 `N8N_IMAGE_WEBHOOK_URL`（可回退 `ANYCROSS_IMAGE_URL`）；如需要鉴权，请在工具内或反向代理添加校验。
2) 传入英文 prompt 与目标保存路径，并可传入作者智能体名称 `author_agent`。
3) 多图参考时传入 `reference_images` (URL 列表) 与 `mode`（`img2img` / `multi_ref`）。

### B. 批量分镜委托 (generate_storyboard_batch)
1) **前置条件**: 
   - 确保 `project` 和 `scene` 在数据库中已初始化（已有 `shots` 数据）。
   - 确保该场次已通过 `FileTool.init_scene_structure` 初始化（数据库中记录了 `file_path`）。
2) **调用参数**:
   - `project`: 项目名称。
   - `scene`: 场号。
   - `scene_design_files`: (可选) 场景概念图/环境图的本地路径列表。
   - `other_design_files`: (可选) 角色、道具设定图的本地路径列表。
3) **行为**:
   - 工具会自动从数据库抓取该场所有镜头的 prompt、镜号、描述。
   - 自动查询该场的输出根目录 (`scene_root_path`)。
   - 自动将本地设计图上传 OSS 并转为 URL。
   - 打包发送给 `N8N_SHOT_WEBHOOK_URL` 触发批量生成流。

## 输出格式示例
- "已委托生成，路径: /app/production/<project>/_Design/<category>/<name>/..."
- "✅ 批量分镜任务已提交 (N8N)..."

## 注意事项
- 目前未默认附带签名/Token；若 n8n 开启验证，请在 GenerationTool 中加入对应 Header 或在网关层校验。
- 确保 target_path 合规，避免注入非法路径或越权目录。


## 📌 特别工作流 (Important Workflow)
在保存概念图和读取时：
你需要知道文本设定和物理美术资产是分离的：
- `save_scene` 和 `get_scene` **只负责**保存和检索场景的世界观和文本设定。它们没有物理图片路径，不能存图或找图！
- 物理图片资产（尤其是大场景概念图）必须使用 `save_design_asset` 保存，并且将 `category` 设为 `'en'` (环境)。
- 当你需要查找已经生成的场景概念图时，**必须**使用 `query_design_assets(project, category='en')`，或者直接 `get_design_asset(project, category='en', name='pXX-scXX-enXX')`！
