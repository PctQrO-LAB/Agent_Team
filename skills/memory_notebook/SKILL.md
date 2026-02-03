---
name: memory_notebook
description: 管理笔记本中的记忆、模式与提示模板的技能
---

# 笔记本知识与记忆技能

## 作用
- 保存/读取 memento（备忘）
- 添加/提升行为模式到长期记忆
- 获取通用提示模板

## 依赖工具函数（AgentNotebook）
- save_memento
- get_memento
- add_pattern
- promote_pattern_to_memory

## 使用说明
1) 写入 memento 前，确认主题、关键信息、时间戳。
2) add_pattern 用于记录行为规律；promote_pattern_to_memory 用于提炼长记忆。
3) 记忆相关功能只处理真实输入内容。

## 输出格式示例
- "已保存备忘：<主题>"
- "新增行为模式：<模式摘要>"
- "已提升模式到长期记忆：<名称>"

## 注意事项
- 不要编造记忆内容；所有信息需来自用户或可信上下文。
- 长记忆提炼时，保持简洁、可验证、可复用。
