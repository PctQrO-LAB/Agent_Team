import json
import os


def load_model_config(config_name: str, override_api_key: str = None) -> dict:
    """
    加载模型配置，支持动态覆盖 API Key，并确保返回字典格式。
    """
    # === 原有逻辑：找文件 ===
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_name = f"{config_name}.json" if not config_name.endswith(".json") else config_name
    config_path = os.path.join(current_dir, "../config", file_name)

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"❌ 找不到配置文件: {config_path}")

    # === 原有逻辑：读 JSON ===
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        raise ValueError(f"❌ 配置文件格式错误: {config_path}")

    # === 🔥 关键修复：确保拿到的是 Dict (解决 pop 报错) ===
    target_config = None
    if isinstance(data, list):
        # 如果是列表，取第一个匹配 config_name 的，或者直接取第一个
        target_config = next((c for c in data if c.get("config_name") == config_name), None)
        if not target_config and data:
            target_config = data[0]
    elif isinstance(data, dict):
        target_config = data

    if not target_config:
        raise ValueError(f"❌ 配置文件 {file_name} 解析为空！")

    # === 🔥 新增逻辑：API Key 覆盖策略 ===
    # 优先级：传入参数 > 环境变量 (config里配的key名) > Config里的死值

    final_api_key = override_api_key  # 1. 先看有没有传参

    if not final_api_key:
        # 2. 没传参，去查环境变量
        env_key = target_config.get("api_key_env")
        if env_key:
            final_api_key = os.environ.get(env_key)

    if not final_api_key:
        # 3. 还没找到，用 config 里的硬编码
        final_api_key = target_config.get("api_key")

    # === 原有逻辑：组装返回 ===
    # 注意：这里我们修改了 api_key 的取值来源
    return {
        "config_name": target_config.get("config_name", config_name),
        "model_name": target_config.get("model_name"),
        "api_key": final_api_key,  # <--- 使用计算出的最终 Key
        "client_kwargs": target_config.get("client_kwargs", {}),
        "generate_args": target_config.get("generate_args", {}),
        "stream": target_config.get("stream", False)
    }

    # 3. 🔥 智能解析 (核心修改点)
    # 不再强制要求 config_name 必须匹配，只要有数据就行
    target_config = None

    if isinstance(data, dict):
        # 情况 A: 你的 JSON 直接是一个 {} 对象
        target_config = data
    elif isinstance(data, list):
        # 情况 B: 你的 JSON 是一个 [] 列表
        # 优先找名字匹配的，找不到就直接拿第一个！不再报错！
        target_config = next((c for c in data if c.get("config_name") == config_name), None)
        if not target_config and len(data) > 0:
            print(f"⚠️ [提示] 文件内未找到 config_name='{config_name}'，自动使用第一条配置。")
            target_config = data[0]

    if not target_config:
        raise ValueError(f"❌ 配置文件 {file_name} 是空的！")

    # 4. 组装参数
    api_key = os.environ.get(target_config.get("api_key_env"))
    if not api_key:
        api_key = target_config.get("api_key")

    if not api_key:
        print(f"⚠️ [警告] 未找到 API Key")

    # 5. 返回结果
    # 强制把 config_name 补上，这样 AgentScope 就不会报错了
    return {
        "model_name": target_config.get("model_name"),
        "api_key": api_key,
        "client_kwargs": target_config.get("client_kwargs", {}),
        "stream": target_config.get("stream", False)
    }

# 自测代码
#if __name__ == "__main__":
    # 试试看，这次肯定能打出来东西
    print(load_model_config("deepseek_config"))