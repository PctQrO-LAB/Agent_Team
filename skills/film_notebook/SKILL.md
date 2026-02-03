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
- AgentNotebook: save_project, save_scene, save_shot, save_design_asset, get_project, get_scene, get_shot, get_design_asset
- FileTool: init_scene_structure, init_shot_structure, init_design_structure, read_image_as_url

## 使用说明
1) 初始化目录：根据需要调用 init_*_structure 建立文件夹。
2) 保存前先询问项目/场景/镜头/资产标识及版本信息。
3) 读取时给出可用条目的摘要（名称、版本、路径）。
4) 如需生成图片与落盘，请交由外部工作流（n8n 等）；本地仅保留读取 URL 的能力。

## 输出格式示例
- "读取设计资产：名称/版本/路径列表"

## 注意事项
- 路径以相对项目根目录描述，避免暴露绝对路径给外部用户。
- 不要覆盖同名文件，建议提示用户确认或生成新版本号。
