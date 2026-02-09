---
name: agent_relay
description: 让智能体之间进行轻量级消息沟通，并可镜像到飞书
---

# 基础技能：Agent 间沟通

## 作用
- 在后端直接把消息转发给目标 Agent。
- 可选同步到飞书指定会话，便于人类监督与追踪。

## 依赖工具函数
- AgentRelayTool: send_agent_message

## 使用说明
1) 传入目标 Agent 名称与消息内容即可触发沟通。
2) 如需在飞书中可见，保持 mirror=True（默认）。
3) 目标 Agent 名称需与系统注册名一致（如 ConceptAgent / ProduceAgent / DesignAgent / StoryboardAgent / Scheduler）。

## 参数
- receiver: 目标 Agent 名称。
- content: 消息内容。
- mirror: 是否镜像到飞书（默认 True）。

## 返回
- 成功返回 “已发送给 <receiver>”。
- 失败返回错误原因。

## 注意事项
- 若未配置飞书镜像会话，mirror 不会生效，但消息仍会发送到目标 Agent。
- 该技能用于 Agent 间协作，不替代对用户的直接回复。
