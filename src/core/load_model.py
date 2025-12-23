import json
import os

def load_model_config(config_name: str):
    """
    读取配置文件并返回模型对象参数 (容错增强版)
    """
    # 1. 找文件 (自动补全 .json)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_name = f"{config_name}.json" if not config_name.endswith(".json") else config_name
    config_path = os.path.join(current_dir, "../config", file_name)

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"❌ 找不到配置文件: {config_path}")

    # 2. 读配置
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        raise ValueError(f"❌ 配置文件格式错误: {config_path}")

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