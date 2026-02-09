---
name: calendar_lark
description: 使用飞书日历和任务 API 进行日程与任务管理的技能
---

# 飞书日程与任务技能

## 作用
- 创建/查询飞书日程
- 创建/查询/删除飞书任务

## 依赖工具函数（已在 LarkToolset 暴露）
- create_calendar_event
- list_calendar_events
- create_task
- list_tasks
- delete_task

## 使用说明
1) 在调用前确保具备 chat_id 或 user_id 上下文（由 Manager 提供）。
2) 日期时间请使用 ISO8601（含时区），如 2024-12-01T09:00:00+08:00。
3) 调用顺序建议：先查询(list)，再创建(create)，必要时删除(delete)。
4) 若需要通知或回显，调用后可用 send_text_message 反馈结果。

## 输出格式示例
- 成功："已创建日程：<标题>，时间：<开始>-<结束>"
- 失败：简述原因并给出下一步（如检查时间格式或权限）。

## 注意事项
- 不要虚构 event_id 或 task_id；只能使用 API 返回值。
- 时间冲突需提示用户由其决定保留或删除旧项。
