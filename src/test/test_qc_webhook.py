import requests
import json
import uuid

# 假设你本地的 webhook 服务跑在 8000 端口
# 如果使用 frp/anycross 等穿透，可以替换为真实的外网地址例如 https://xxx.anycross.com/qc
WEBHOOK_URL = "http://127.0.0.1:8000/qc"

def test_n8n_mock_callback():
    print(f"🚀 发送模拟的 N8N 图片生成回调到: {WEBHOOK_URL}")
    print("-" * 50)
    
    # 模仿 n8n 的回调 Payload （我们之前定义过 source="n8n" 会被无缝拦截）
    payload = {
        "source": "n8n",  
        # 我们模拟两张图的批量交付，附带资产ID和设定描述
        "text": """
📦 【n8n 生成回传任务】已完成！
请查收以下资产进行审核：

1. 资产: P01-ch01
   描述 (Describe): 一名戴着黑色墨镜的赛博朋克特工，穿着黑色皮衣，站在雨夜的霓虹小巷中。
   图片: https://dummyimage.com/600x400/000/fff&text=Cyber_Agent_1

2. 资产: P01-ch02
   描述 (Describe): 同一名特工，侧面视角，由于是侧面能看到他脖子上的机械神经接口，背景同样是霓虹灯。
   图片: https://dummyimage.com/600x400/000/fff&text=Cyber_Agent_2
        """,
        # 给个随机的模拟 chat_id 或留空（留空可能走系统默认回传或者中继）
        "chat_id": "test_chat_123456"     
    }
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload, headers={"Content-Type": "application/json"})
        print(f"📡 HTTP 状态码: {response.status_code}")
        print(f"📄 返回结果: {response.text}")
        if response.status_code == 200:
            print(f"✅ 发送成功！请切换到运行主程序的终端，观察 QCAgent 是否开始思考和执行审核任务。")
    except requests.exceptions.ConnectionError:
        print(f"❌ 请求失败：无法连接到 {WEBHOOK_URL}，请检查主程序 launch.py 是否已启动。")
    except Exception as e:
        print(f"❌ 请求发生异常: {e}")

if __name__ == "__main__":
    test_n8n_mock_callback()
