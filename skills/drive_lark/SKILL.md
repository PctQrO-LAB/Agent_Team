---
name: drive_lark
description: 飞书云盘基础技能（精简版）
---

# 飞书云盘技能

## 作用
- 获取项目专属文件夹下的文件清单（包含文档名称、Token 和 URL）
- **读取在线文档 (docx) 的纯文本内容**。支持直接传入文档 Token 或完整的飞书云文档 URL。

## 依赖工具函数
- list_files_in_folder: 获取硬编码的项目文件夹内的文件列表。无需参数。
- read_document_content: 读取指定的 docx 文档内容。参数 `document_id` 可以是文档 Token 或 URL。

## 使用说明
1) 当用户询问项目文档、资料或查看云盘文件时，首先调用 `list_files_in_folder` 查看有哪些文件。
2) 从列表中获取感兴趣的文档 Token 或 URL。
3) 使用 `read_document_content` 读取该文档的具体内容。
4) **注意**：该工具只支持读取新版文档 (docx)，不支持旧版 (doc) 或表格 (sheet)。

## 输出格式示例
- "📂 文件夹内容 (Ygpuf...):"
- "- [docx] 需求文档 (Token: xxx) URL: ..."
- "云文档\n多人实时协同，插入一切元素..." (文档内容)

## 注意事项
- 文件夹 ID 是预设的，Agent 无法更改查询目录。
- 读取内容时，如果输入是 URL，工具内部会自动提取 Token。

