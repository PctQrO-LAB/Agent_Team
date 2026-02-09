import os
import sys
import oss2
from dotenv import load_dotenv

# --- 路径设置 ---
# 确保能找到项目根目录下的 .env 文件
current_dir = os.path.dirname(os.path.abspath(__file__))
# 假设脚本在 src/test/，.env 在项目根目录 (../../.env)
root_dir = os.path.dirname(os.path.dirname(current_dir))
env_path = os.path.join(root_dir, '.env')


def run_test():
    print("🚀 正在启动 OSS 连通性测试...")

    # 1. 加载配置
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"📂 已加载配置文件: {env_path}")
    else:
        print("⚠️ 未找到本地 .env 文件，尝试使用系统环境变量...")

    # 2. 读取变量
    ak_id = os.environ.get("OSS_ACCESS_KEY_ID")
    ak_secret = os.environ.get("OSS_ACCESS_KEY_SECRET")
    bucket_name = os.environ.get("OSS_BUCKET_NAME")
    endpoint = os.environ.get("OSS_ENDPOINT")

    # 打印脱敏信息以供检查
    print("-" * 40)
    print(f"🔑 AccessKey ID:     {ak_id[:6]}******" if ak_id else "❌ 未配置")
    print(f"📦 Bucket Name:      {bucket_name}" if bucket_name else "❌ 未配置")
    print(f"🌐 Endpoint:         {endpoint}" if endpoint else "❌ 未配置")
    print("-" * 40)

    if not all([ak_id, ak_secret, bucket_name, endpoint]):
        print("❌ 错误：OSS 配置缺失，请检查 .env 文件！")
        return

    try:
        # 3. 初始化连接
        print("🔌 正在连接阿里云 OSS...")
        auth = oss2.Auth(ak_id, ak_secret)
        bucket = oss2.Bucket(auth, endpoint, bucket_name)

        # 4. 执行上传测试
        object_name = "test_connectivity_check.txt"
        content = "✅ Hello! Your Agent Team OSS connection is working perfectly."

        print(f"⬆️  正在尝试上传测试文件: {object_name} ...")
        result = bucket.put_object(object_name, content)

        if result.status == 200:
            print("✅ 上传成功！")

            # 5. 执行生成链接测试 (VLM 读取图片的关键能力)
            url = bucket.sign_url('GET', object_name, 60)
            print(f"🔗 生成测试链接 (60秒有效): \n{url}")
            print("\n🎉 恭喜！OSS 配置完全正确，Agent 可以正常收发图片了。")
        else:
            print(f"❌ 上传可能失败，返回状态码: {result.status}")

    except oss2.exceptions.OssError as e:
        print(f"\n❌ OSS 报错:")
        print(f"   Status: {e.status}")
        print(f"   Code:   {e.code}")
        print(f"   Message: {e.message}")
        print(f"   RequestID: {e.request_id}")
        print("💡 提示：如果是 403 Forbidden，请检查 RAM 账号是否有 AliyunOSSFullAccess 权限。")
    except Exception as e:
        print(f"\n❌ 系统异常: {e}")


if __name__ == "__main__":
    run_test()