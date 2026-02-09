import requests
import time

# ================= 配置区域 =================
# 公网地址（FRP 暴露出的地址+路径）
PUBLIC_URL = "http://frp-own.com:52316/design"

# 本地直连地址（容器内 0.0.0.0:8000 或宿主映射）
LOCAL_URL = "http://127.0.0.1:8000/design"

# 模拟飞书验证数据（记得把 token 换成该应用的 Verification Token）
TEST_PAYLOAD = {
    "type": "url_verification",
    "challenge": "SUCCESS_IF_YOU_SEE_THIS",
    "token": "vC5erFOQ0fxQwsMw10AYSEAj1Y412DOt",
}
# ===========================================


def test_connection(name, url):
    print(f"\n--- 正在测试: {name} ---")
    print(f"目标地址: {url}")

    try:
        start_time = time.time()
        response = requests.post(url, json=TEST_PAYLOAD, timeout=5)
        duration = (time.time() - start_time) * 1000

        print(f"✅ 连接成功! (耗时: {duration:.2f}ms)")
        print(f"状态码: {response.status_code}")
        print(f"返回内容: {response.text}")

        try:
            resp_json = response.json()
            if resp_json.get("challenge") == TEST_PAYLOAD["challenge"]:
                print("🎉 验证通过！challenge 对得上。")
            else:
                print("⚠️  连接通了，但 challenge 不匹配。")
        except Exception:
            print("⚠️  连接通了，但返回的不是 JSON。")

    except requests.exceptions.ConnectionError:
        print("❌ 连接失败: 无法连接到服务器。")
        if name == "公网 (FRP)":
            print("   -> 检查 FRP 隧道是否启动、remote_port/local_port 是否对。")
        else:
            print("   -> 检查容器/服务是否启动，端口映射是否对。")
    except requests.exceptions.Timeout:
        print("❌ 连接超时: 服务器响应太慢。")
    except Exception as e:
        print(f"❌ 发生错误: {e}")


if __name__ == "__main__":
    print("🚀 开始全链路连通性测试...")
    test_connection("本地直连", LOCAL_URL)
    test_connection("公网 (FRP)", PUBLIC_URL)