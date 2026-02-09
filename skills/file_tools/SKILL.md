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
