
import requests
import json
import time
import os
from dotenv import load_dotenv # 引入加载库

# 1. 先加载 .env 文件
load_dotenv()

# 2. 再获取变量
WEBHOOK_URL = os.environ.get("ANYCROSS_IMAGE_URL")

# 3. 加上这个调试打印，一眼就能看出是否获取成功
print(f"Debug: WEBHOOK_URL is {WEBHOOK_URL}")

if WEBHOOK_URL is None:
    print("❌ 错误：未找到环境变量 ANYCROSS_IMAGE_URL")
    exit(1)

# 2. 模拟的测试数据
TEST_PAYLOAD = {
    "prompt": "A cyberpunk cat wearing sunglasses, neon lights, high resolution",
    "target_path": "/app/production/Test_Project/_Design/character/cyber_cat_v1.jpg"
}


# ===========================================

def test_cloud_generation():
    print(f"🚀 [Start] 正在发送请求给飞书集成平台...")
    print(f"🔗 URL: {WEBHOOK_URL[:40]}...")
    print(f"📦 Payload: {json.dumps(TEST_PAYLOAD, indent=2)}")

    start_time = time.time()

    try:
        # 发送 POST 请求
        # 注意：这里 headers 只要 standard json 即可，不需要鉴权（除非你在触发器设了白名单）
        response = requests.post(
            WEBHOOK_URL,
            json=TEST_PAYLOAD,
            headers={"Content-Type": "application/json"},
            timeout=10  # 给个超时时间防止卡死
        )

        duration = time.time() - start_time

        # 打印结果
        print(f"\n⏱️ 耗时: {duration:.2f}秒 (仅包含握手时间)")

        if response.status_code == 200:
            print(f"✅ [Success] 飞书平台已接收指令！")
            print(f"📡 响应内容: {response.text}")
            print("\n👀 下一步操作：")
            print("请立刻去你的【飞书项目群】查看，Bot 应该会发送一条包含 JSON 的消息。")
            print("如果群里没反应，请去集成平台的【运行日志】里查错。")
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