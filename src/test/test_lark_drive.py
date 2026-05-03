import os
import sys
from dotenv import load_dotenv

# Add project root to path so we can import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.tools.lark_drive_tools import LarkDriveTool

def main():
    # 1. Load Environment Variables
    load_dotenv()
    
    print("🚀 正在初始化 LarkDriveTool...")
    
    # 尝试从环境变量获取 (优先使用 Storyboard 的配置，根据用户指定)
    app_id = os.environ.get("STORYBOARD_APP_ID") or os.environ.get("ASSISTANT_APP_ID")
    app_secret = os.environ.get("STORYBOARD_APP_SECRET") or os.environ.get("ASSISTANT_APP_SECRET")

    if not app_id or not app_secret:
        print("❌ 错误: 未找到 APP_ID 或 APP_SECRET 环境变量。")
        print("请确保 .env 文件存在或环境变量已设置。")
        return

    drive_tool = LarkDriveTool(app_id, app_secret)

    # Step 1: List Files
    print("\n📋 [Step 1] 获取文件夹文件列表...")
    file_list_str = drive_tool.list_files_in_folder()
    print("-" * 40)
    print(file_list_str)
    print("-" * 40)

    # Step 2: Read Document
    print("\n📖 [Step 2] 测试读取文档内容")
    doc_id = input("👉 请输入要在上面列表中读取的文档 Token (或 URL): ").strip()

    if not doc_id:
        print("⚠️ 未输入 Token，测试结束。")
        return

    print(f"\n正在读取文档: {doc_id} ...")
    content = drive_tool.read_document_content(doc_id)
    
    print("-" * 40)
    print("📄 文档内容预览 (前 500 字符):")
    print(content[:500] + ("..." if len(content) > 500 else ""))
    print("-" * 40)

if __name__ == "__main__":
    main()
