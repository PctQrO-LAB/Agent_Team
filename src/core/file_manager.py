import os
import json
import base64
import logging
import oss2
from typing import Optional, Dict

logger = logging.getLogger("FileManager")


class FileManager:
    """
    [全能文件管家] Core Layer
    集成了 "架构管理"、"物理读写" 和 "云端桥接" 三位一体的核心模块。

    职责：
    1. 搭建剧组场地 (Init Directory Structure).
    2. 管理本地资产 (Read/Write Local Files).
    3. 自动同步云端 (Auto-Sync to OSS).
    """

    ROOT_PATH = "/app/production"

    def __init__(self):
        # --- 1. 初始化 OSS 连接 (原 MediaBridge 逻辑) ---
        self.bucket_name = os.environ.get("OSS_BUCKET_NAME")
        self.endpoint = os.environ.get("OSS_ENDPOINT")
        self.key_id = os.environ.get("OSS_ACCESS_KEY_ID")
        self.key_secret = os.environ.get("OSS_ACCESS_KEY_SECRET")

        self.bucket = None
        self._init_oss()

    def _init_oss(self):
        if self.key_id and self.key_secret:
            try:
                auth = oss2.Auth(self.key_id, self.key_secret)
                self.bucket = oss2.Bucket(auth, self.endpoint, self.bucket_name)
                logger.info("☁️ [FileManager] OSS Link Established (Integrated)")
            except Exception as e:
                logger.error(f"❌ [FileManager] OSS Connection Failed: {e}")

    # =================================================
    # 🏗️ 场地搭建 (Stage Setup / Architecture)
    # =================================================

    def _ensure_dir(self, path: str) -> str:
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
            logger.info(f"📂 Directory Created: {path}")
        return path

    def init_project(self, project: str) -> str:
        """初始化项目根目录"""
        return self._ensure_dir(os.path.join(self.ROOT_PATH, project))

    def init_scene(self, project: str, scene: str) -> str:
        """初始化场景目录 (包含概念设计区)"""
        # 结构: Project/Scene/_Concept
        base = self._ensure_dir(os.path.join(self.ROOT_PATH, project, scene))
        self._ensure_dir(os.path.join(base, "_Concept"))
        return base

    def init_character(self, project: str, name: str) -> str:
        """初始化角色目录"""
        # 结构: Project/_Character/Name
        return self._ensure_dir(os.path.join(self.ROOT_PATH, project, "_Character", name))

    def init_shot(self, project: str, scene: str, shot: str, version: int) -> str:
        """初始化镜头版本目录"""
        # 结构: Project/Scene/Shot/v1
        return self._ensure_dir(os.path.join(self.ROOT_PATH, project, scene, shot, f"v{version}"))

    # =================================================
    # 💾 物理动作 (Physical I/O)
    # =================================================

    def save_json(self, dir_path: str, file_name: str, content: Dict) -> str:
        """保存 JSON (自动校验路径安全性)"""
        if not dir_path.startswith(self.ROOT_PATH):
            raise ValueError(f"Access Denied: {dir_path}")

        full_path = os.path.join(dir_path, file_name)
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        return full_path


    # =================================================
    # ☁️ 自动桥接 (Auto-Bridge)
    # =================================================

    def get_file_url(self, local_path: str) -> Optional[str]:
        """
        [核心能力] 获取文件的云端链接。
        机制：Agent 只要想看这个本地文件，我就自动把它同步到 OSS 并给出一个 URL。
        """
        if not local_path or not os.path.exists(local_path):
            return None

        if not self.bucket:
            logger.warning("OSS not initialized, cannot bridge file.")
            return None

        try:
            # 构造 OSS Key: 去除本地绝对路径前缀
            # /app/production/Movie/Scene/img.jpg -> assets/Movie/Scene/img.jpg
            relative_path = local_path.replace(self.ROOT_PATH, "")
            if relative_path.startswith("/"): relative_path = relative_path[1:]

            oss_key = f"assets/{relative_path}"

            # 1. 上传 (覆盖式，确保最新)
            self.bucket.put_object_from_file(oss_key, local_path)

            # 2. 签名 (生成临时可访问 URL)
            url = self.bucket.sign_url('GET', oss_key, 3600)
            return url

        except Exception as e:
            logger.error(f"❌ [Auto-Bridge] Sync Failed: {e}")
            return None