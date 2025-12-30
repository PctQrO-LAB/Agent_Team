import time
import datetime
import pytz
from typing import Optional


class TimeUtils:
    """
    统一时间处理工具，解决飞书 API 中秒(Calendar)与毫秒(Task)混用的问题。
    默认时区：Asia/Shanghai
    """
    TZ_CN = pytz.timezone("Asia/Shanghai")

    @classmethod
    def get_now_dt(cls) -> datetime.datetime:
        """获取当前带时区的时间对象"""
        return datetime.datetime.now(cls.TZ_CN)

    @classmethod
    def parse_time(cls, time_str: str) -> Optional[datetime.datetime]:
        """
        将各类时间字符串解析为带时区的 datetime 对象。
        支持：
        - "2025-12-30 14:00:00"
        - "2025-12-30T14:00:00"
        """
        if not time_str:
            return None

        try:
            # 1. 尝试 ISO 格式 (带T)
            if "T" in time_str:
                dt = datetime.datetime.fromisoformat(time_str)
            # 2. 尝试常规格式 (空格分隔)
            else:
                dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")

            # 3. 补全时区 (如果没带时区，默认当作北京时间)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=cls.TZ_CN)
            return dt
        except ValueError:
            return None

    @classmethod
    def to_ms_timestamp(cls, time_str: str) -> Optional[str]:
        """[Task专用] 转为毫秒级时间戳字符串"""
        dt = cls.parse_time(time_str)
        if not dt: return None
        return str(int(dt.timestamp() * 1000))

    @classmethod
    def to_sec_timestamp(cls, time_str: str) -> Optional[str]:
        """[Calendar专用] 转为秒级时间戳字符串"""
        dt = cls.parse_time(time_str)
        if not dt: return None
        return str(int(dt.timestamp()))

    @classmethod
    def ms_to_datetime_str(cls, ms_timestamp: str) -> str:
        """将毫秒时间戳转回可读字符串"""
        try:
            ts = int(ms_timestamp) / 1000
            dt = datetime.datetime.fromtimestamp(ts, cls.TZ_CN)
            return dt.strftime('%Y-%m-%d %H:%M')
        except:
            return "未知时间"