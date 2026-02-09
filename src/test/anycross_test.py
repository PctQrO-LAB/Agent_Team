
import requests
import json
import time
import os
from dotenv import load_dotenv # 引入加载库

# 1. 先加载 .env 文件
load_dotenv()

# 2. 再获取变量（优先使用 n8n）
WEBHOOK_URL = os.environ.get("N8N_IMAGE_TEST_WEBHOOK_URL") or os.environ.get("ANYCROSS_IMAGE_URL")
# 可选：n8n Webhook Token（如果你在 n8n 节点里开启了认证）
WEBHOOK_TOKEN = os.environ.get("N8N_WEBHOOK_TOKEN")

# 3. 加上这个调试打印，一眼就能看出是否获取成功
print(f"Debug: WEBHOOK_URL is {WEBHOOK_URL}")
print(f"Debug: WEBHOOK_TOKEN is {'SET' if WEBHOOK_TOKEN else 'NOT SET'}")

if WEBHOOK_URL is None:
    print("❌ 错误：未找到环境变量 N8N_IMAGE_WEBHOOK_URL 或 ANYCROSS_IMAGE_URL")
    exit(1)

# 2. 模拟的测试数据
TEST_PAYLOAD = {
    "prompt": "Subject: A sprawling cyberpunk slum district at night, built on decaying concrete megastructures and stacked shipping containers. Walls are plastered with flickering holographic ads, cracked LED billboards, and scrolling data streams in Chinese, Japanese, and Cyrillic. A lone figure in a worn synth-leather coat walks below, head down, face half-hidden by a static-glitching visor. Rain-slicked streets reflect fractured neon signs (magenta, electric cyan, toxic green), but the air is thick with cold mist and the hum of overloaded servers.Style/Medium: Concept art, Unreal Engine 5 render, cinematic lighting, hyper-detailed, volumetric fog, Blade Runner 2049 meets Ghost in the Shell aesthetic.Color: Extremely saturated neon palette (hot pink, acid green, cobalt blue) contrasted with desaturated greys, frosted metal, and icy blues in shadows. No warm tones — even firelight is replaced by emergency strobes or coolant leaks.Camera/Composition: Wide-angle low-angle shot from street level, looking up at towering ad-facades; shallow depth of field with foreground raindrops on lens. One central vertical beam of light cuts through smog — revealing a broken surveillance drone hovering silently.Quality: 8K resolution, photorealistic, intricate surface detail (corrosion, peeling paint, fiber-optic fraying), film grain, subtle chromatic aberration.Negative Prompt: warm lighting, sunlight, clean surfaces, smiling people, nature, organic textures, wood, grass, cozy, inviting, symmetrical composition, cartoon, anime, sketch, blurry background.",
    "target_path": "/app/production/cyber_city/s1/_Concept/cyber_city_v1.png",
    "author_agent": "ConceptAgent",
}


# ===========================================

def test_cloud_generation():
    print(f"🚀 [Start] 正在发送请求给 n8n Webhook...")
    print(f"🔗 URL: {WEBHOOK_URL[:40]}...")
    print(f"📦 Payload: {json.dumps(TEST_PAYLOAD, indent=2)}")

    start_time = time.time()

    try:
        # 发送 POST 请求
        # 注意：这里 headers 只要 standard json 即可，不需要鉴权（除非你在触发器设了白名单）
        headers = {"Content-Type": "application/json"}
        if WEBHOOK_TOKEN:
            headers["X-Webhook-Token"] = WEBHOOK_TOKEN

        response = requests.post(WEBHOOK_URL, json=TEST_PAYLOAD, headers=headers, timeout=10)

        duration = time.time() - start_time

        # 打印结果
        print(f"\n⏱️ 耗时: {duration:.2f}秒 (仅包含握手时间)")

        if response.status_code == 200:
            print(f"✅ [Success] n8n 已接收指令！")
            print(f"📡 响应内容: {response.text}")
            print("\n👀 下一步操作：")
            print("请在 n8n 执行日志查看节点是否成功，以及下游（如飞书/存储）是否有响应。")
        else:
            print(f"❌ [Failed] 请求被拒绝。")
            print(f"Status Code: {response.status_code}")
            print(f"Error Msg: {response.text}")

    except Exception as e:
        print(f"❌ [Error] 连接异常: {e}")


if __name__ == "__main__":
    if "xxxxxxxx" in WEBHOOK_URL:
        print("⚠️ 请先修改代码中的 WEBHOOK_URL 为真实地址！")
    else:
        test_cloud_generation()