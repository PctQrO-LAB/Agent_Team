import sys
import os

src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(src_path))
sys.path.insert(0, src_path)

from src.tools.generate_tools import GenerationTool
from src.tools.note_tools import AgentNotebook

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(src_path), ".env"))

def main():
    print("🚀 开始测试 generate_image_batch 工具...")
    
    # 在测试环境中，强制将默认 webhook 环境变量覆盖为 TEST webhook
    test_batch_url = os.environ.get("N8N_IMAGE_BATCH_TEST_WEBHOOK_URL")
    if test_batch_url:
        os.environ["N8N_IMAGE_BATCH_WEBHOOK_URL"] = test_batch_url
    
    note_tool = AgentNotebook("TestAgent")
    gen_tool = GenerationTool()
    
    print("\n📝 1. 在数据库中登记测试资产...")
    res1 = note_tool.save_design_asset(
        project="p01", 
        category="character", 
        describe="A cute little robot with glowing eyes", 
        image_path="/app/production/p01/_Design/character/p01-ch99/p01-ch99.jpg",
        name="TestRobot"
    )
    print("保存角色: OK")

    res2 = note_tool.save_scene(
        project="p01",
        scene="p01-sc99",
        world_prompt="A futuristic cyber city",
        elements="Neon lights, flying cars",
        mood="Cyberpunk, dark"
    )
    print("保存场景: OK")
    
    print("\n📸 2. 调用 generate_image_batch...")
    import sqlite3
    db_path = os.path.join(os.path.dirname(src_path), "data", "shared", "agent_shared.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT uid FROM design_assets ORDER BY id DESC LIMIT 1")
    uid_ch = c.fetchone()[0]
    
    c.execute("SELECT uid FROM scenes ORDER BY id DESC LIMIT 1")
    uid_sc = c.fetchone()[0]
    conn.close()

    asset_ids = [uid_ch, uid_sc, "fake-id-001"]
    print(f"传入资产 IDs: {asset_ids}")
    
    try:
        response = gen_tool.generate_image_batch(
            asset_ids=asset_ids,
            author_agent="TestAgent",
            mode="text2img"
        )
        print("\n✅ 批量生图工具响应:")
        # parse dict responses gracefully
        if hasattr(response, 'content'):
            if isinstance(response.content[0], dict) and "text" in response.content[0]:
                print(response.content[0]["text"])
            elif hasattr(response.content[0], "text"):
                print(response.content[0].text)
            else:
                print(response)
        else:
            print(response)
            
    except Exception as e:
        print(f"❌ 运行出错: {e}")

if __name__ == "__main__":
    main()
