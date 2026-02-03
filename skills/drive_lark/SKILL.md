---
name: drive_lark
description: 使用飞书云盘进行文件存取与列举的技能
---

# 飞书云盘技能

## 作用
- 上传文件到飞书云盘
- 读取云盘文件为 base64
- 列举文件夹内容
- （可选）从消息下载图片到本地后再上传

## 依赖工具函数（LarkToolset）
- upload_file
- read_file_base64
- list_folder_files
- download_message_image（如需从消息取图）
- extract_token_from_url（解析分享链接 token）

## 使用说明
1) 上传前确认文件本地路径和目标 folder_token。
2) 读取/列举时需要有效的 file_token 或 folder_token。
3) 大文件操作时先提示用户可能的耗时与大小限制。

## 输出格式示例
- "已上传文件：<文件名>，folder=<folder_token>"
- "文件列表：<名称/类型/大小>..."
- "已读取文件为 base64（长度 N）"

## 注意事项
- 不要泄露访问密钥；仅返回必要的 token/路径。
- 对用户提供的分享链接，先用 extract_token_from_url 提取 token 再操作。
