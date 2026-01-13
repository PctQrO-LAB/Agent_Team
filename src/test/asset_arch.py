import sys
import os
import time

# 路径修补
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.tools.note_tools import AgentNotebook
from src.tools.file_tools import FileTool


# === 🛠️ 修复核心：安全提取文本的辅助函数 ===
def get_text(response):
    """
    兼容处理：无论 response.content[0] 是对象还是字典，都能正确取值。
    """
    if not response.content:
        return "❌ 无返回内容"

    item = response.content[0]

    # 情况 A: item 是字典 (本次报错的原因)
    if isinstance(item, dict):
        return item.get("text", str(item))

    # 情况 B: item 是对象 (AgentScope 标准行为)
    return getattr(item, "text", str(item))


def test_architecture():
    print("🏗️ 正在测试【双层资产架构】基础设施...")

    # 1. 初始化工具
    db_tool = AgentNotebook(agent_name="TestBot")
    fs_tool = FileTool()

    # ⚠️ 强制指定为 Mac 上的真实测试目录
    # 请确保这个文件夹你自己手动新建好了，或者脚本有权限创建它
    # ✅ 既然在 Docker 里跑，就让它使用 FileSysTool 默认定义的 "/app/production"
    print(f"⚠️ 正在向容器挂载点写入: {fs_tool.ROOT_PATH}")

    # 2. 模拟场景：Agent 决定创建 "流浪地球3 - 第1场 - 第1镜"
    project = "WanderingEarth3"
    scene = "Scene_01"
    shot = "Shot_01"

    # 2.1 获取版本号 (逻辑层)
    last_ver = db_tool.get_latest_version(project, scene, shot)
    new_ver = last_ver + 1
    print(f"\n[1] 逻辑层计算: 当前是 v{new_ver}")

    # 2.2 创建物理文件夹 (物理层)
    print(f"[2] 物理层操作: 正在创建文件夹...")
    res = fs_tool.init_shot_structure(project, scene, shot, new_ver)

    # 🔥 修复点 1：使用 get_text
    dir_path = get_text(res)
    print(f"    >>> 目录已就绪: {dir_path}")

    # 2.3 写入 Prompt 文件 (物理层)
    print(f"[3] 物理层操作: 正在写入 prompt.json...")
    prompt_data = {
        "description": "A cyberpunk city street at night, neon lights, rain.",
        "model": "midjourney",
        "params": "--ar 16:9 --v 6.0"
    }
    res_write = fs_tool.save_prompt_file(dir_path, prompt_data)

    # 🔥 修复点 2：使用 get_text
    print(f"    >>> {get_text(res_write)}")

    # 2.4 注册资产 (逻辑层)
    print(f"[4] 逻辑层操作: 注册到数据库...")
    final_file_path = os.path.join(dir_path, "prompt.json")
    res_reg = db_tool.register_asset(project, scene, shot, final_file_path, new_ver)

    # 🔥 修复点 3：使用 get_text
    print(f"    >>> {get_text(res_reg)}")

    # 3. 验证结果
    print("\n🔍 [验证] 查询数据库最终状态:")
    res_query = db_tool.query_note("production_assets", {"project": project, "version": new_ver})

    # 🔥 修复点 4：使用 get_text
    print(get_text(res_query))


if __name__ == "__main__":
    test_architecture()