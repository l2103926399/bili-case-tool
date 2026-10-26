"""全局配置：路径、端口、抓取与频控参数。"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = BASE_DIR / "backups"
DB_PATH = DATA_DIR / "bili_case.db"

HOST = "0.0.0.0"
PORT = 8000

# 搜索缓存有效期（秒）：24 小时
CACHE_TTL_SECONDS = 24 * 3600

# 抓取参数
BILI_SEARCH_PAGE_SIZE = 50      # 向 B站 请求的条数
SEARCH_MAX_RESULTS = 24         # 单次搜索最多处理/展示的条数
DETAIL_INTERVAL = 0.15          # 相邻两次详情请求的最小间隔（秒）
DETAIL_CONCURRENCY = 5          # 详情并发数
REQUEST_TIMEOUT = 10.0          # 单请求超时（秒）
MAX_RETRIES = 3                 # 失败重试次数

# 公共部署的自我保护（防止被刷、防止服务器 IP 被 B站 风控）
RATE_LIMIT_PER_MINUTE = 12      # 单个 IP 每分钟最多搜索次数
GLOBAL_SEARCH_CONCURRENCY = 2   # 同时进行的搜索任务上限

# B站接口
BILI_SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
BILI_VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
BILI_NAV_URL = "https://api.bilibili.com/x/web-interface/nav"

# 注意：实测完整 Chrome 长 UA 会触发 B站 412 风控，使用短版 UA 可通过
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
REFERER = "https://www.bilibili.com/"

# 时间范围选项
TIME_RANGES = {
    "all": None,
    "7d": 7,
    "30d": 30,
    "90d": 90,
}
