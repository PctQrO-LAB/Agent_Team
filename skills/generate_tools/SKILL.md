---
name: generate_tools
description: 通过 n8n Webhook 委托生成图片/触发工作流
---

# 生成委托技能

## 作用
- 将 prompt 与目标路径发送到 n8n Webhook，触发生图或后续处理。

## 依赖工具函数
- GenerationTool: generate_image

## 使用说明
1) 确认环境已配置 `N8N_IMAGE_WEBHOOK_URL`（可回退 `ANYCROSS_IMAGE_URL`）；如需要鉴权，请在工具内或反向代理添加校验。
2) 传入英文 prompt 与目标保存路径，并可传入作者智能体名称 `author_agent`；若工作流支持自动创建目录，直接按约定路径填写即可。
3) 多图参考时传入 `reference_images` (URL 列表) 与 `mode`（如 `img2img` / `multi_ref`）。
4) 如工作流需要更多参数，请在 prompt 中说明或扩展 payload 规范后再调整工具。

## 输出格式示例
- "已委托生成，路径: /app/production/<project>/_Design/<category>/<name>/..."

## 注意事项
- 目前未默认附带签名/Token；若 n8n 开启验证，请在 GenerationTool 中加入对应 Header 或在网关层校验。
- 确保 target_path 合规，避免注入非法路径或越权目录。
