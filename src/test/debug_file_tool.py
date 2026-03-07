import os
import sys
from dotenv import load_dotenv

# Add project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load env
load_dotenv()

from src.core.file_manager import FileManager

def debug():
    print("🚀 Starting Debug for File Directory and OSS...")
    
    # Check Environment
    print(f"Checking /app/production existence: {os.path.exists('/app/production')}")
    print(f"CWD: {os.getcwd()}")
    
    fm = FileManager()
    print(f"FileManager Initialized. ROOT_PATH: {fm.ROOT_PATH}")
    
    # Check OSS Status
    print(f"OSS Bucket Object: {fm.bucket}")
    if fm.bucket:
        print("✅ OSS Object created (Auth success not guaranteed yet)")
    else:
        print("❌ OSS Object is None. Check env vars.")
        print(f"ID: {os.environ.get('OSS_ACCESS_KEY_ID')}")
        print(f"SECRET: {os.environ.get('OSS_ACCESS_KEY_SECRET')}")
    
    # Test Path Logic
    input_path = "app/production/cyber_city/s5/concept/s5_v2_dark_bar.jpg"
    print(f"\n🧪 Testing Input Path: {input_path}")
    
    # Manually mimic logic
    local_path = input_path
    real_path = local_path
    if local_path.startswith("app/production"):
         real_path = local_path.replace("app/production", fm.ROOT_PATH)
    
    print(f"Resolved 'real_path': {real_path}")
    print(f"Does real_path exist? {os.path.exists(real_path)}")
    
    # Test Function
    print("\nExecuting get_file_url()...")
    try:
        url = fm.get_file_url(input_path)
        print(f"Result URL: {url}")
    except Exception as e:
        print(f"❌ Exception during execution: {e}")

if __name__ == "__main__":
    debug()
