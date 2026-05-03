import sys
import os
from dotenv import load_dotenv

# 确保能导入 src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

# 手动加载根目录的 .env 文件
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.env"))
if os.path.exists(env_path):
    load_dotenv(env_path)
    print(f"🔧 [Env] Loaded .env from {env_path}")
else:
    print(f"⚠️ [Env] .env file not found at {env_path}")

from src.tools.generate_tools import GenerationTool

def main():
    print("\n🤖 [模拟 Agent] 准备调用 GenerationTool...")
    print("-----------------------------------------------")
    
    # 1. 交互式输入参数
    # 如果存在测试用的 Webhook URL，在测试环境中优先使用它覆写正式 URL
    test_url = os.environ.get("N8N_SHOT_TEST_WEBHOOK_URL")
    if test_url:
        print(f"🔧 [Test Mode] Switching to Test URL: {test_url}")
        os.environ["N8N_SHOT_WEBHOOK_URL"] = test_url

    project = input("Please enter Project Name (e.g. MyFilm): ").strip()
    if not project:
        print("❌ Project cannot be empty.")
        return

    scene = input("Please enter Scene Number (e.g. 1): ").strip()
    if not scene:
        print("❌ Scene cannot be empty.")
        return

    # root_path = input("Scene Root Path (e.g. /app/production/MyFilm/1): ").strip()
    # if not root_path:
    #     root_path = "/app/production/DEFAULT_TEST"

    ref_scene = input("Scene Design Path (Optional): ").strip()
    scene_refs = [ref_scene] if ref_scene else None
    
    ref_other = input("Other Design Path (Optional): ").strip()
    other_refs = [ref_other] if ref_other else None

    # 2. 实例化工具
    print(f"\n🚀 Calling generate_storyboard_batch({project}, {scene})...")
    tool = GenerationTool()

    # 3. 真实调用
    try:
        response = tool.generate_storyboard_batch(
            project, 
            scene,
            scene_design_files=scene_refs,
            other_design_files=other_refs
        )
        
        print("\n📝 [Tool Response]:")
        for block in response.content:
            # 兼容对象属性访问和字典键值访问
            text = getattr(block, 'text', None)
            if text is None and isinstance(block, dict):
                text = block.get('text', str(block))
            
            print(f"---\n{text}\n---")
            
    except Exception as e:
        print(f"\n❌ Exception: {e}")

if __name__ == "__main__":
    main()
