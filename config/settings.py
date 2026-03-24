from pathlib import Path
import os
import environ
import sys

# 1. 환경변수
env = environ.Env(
    DEBUG=(bool, False)
)
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, os.path.join(BASE_DIR, 'apps'))
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])
ALLOWED_CIDR_NETS = env.list('ALLOWED_CIDR_NETS', default=['10.1.0.0/16'])

# 2. 앱 설정
INSTALLED_APPS = [
    'django.contrib.staticfiles',

    # Third Party
    'corsheaders',

    # Local Apps
    'common',
    'notifications',
]

MIDDLEWARE = [
    'allow_cidr.middleware.AllowCIDRMiddleware',
    'corsheaders.middleware.CorsMiddleware', # 최상단
    'django.middleware.security.SecurityMiddleware',
    'common.middleware.AutoBanMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
            ],
        },
    },
]
WSGI_APPLICATION = 'config.wsgi.application'

# 3. 데이터베이스
# Notifications service is DB-less at runtime and uses DynamoDB for reads/writes.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.dummy",
    }
}

# 4. 비밀번호 검증
AUTH_PASSWORD_VALIDATORS = []

# 5. 언어 및 시간
LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'

# 6. Trailing Slash 제거
APPEND_SLASH = False

# 7. CORS 설정
CORS_ALLOW_ALL_ORIGINS = DEBUG
if not DEBUG:
    CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])

# 7-1. Internal API routing (service-to-service)
USE_INTERNAL_SERVICE_API = env.bool("USE_INTERNAL_SERVICE_API", default=False)
AUTH_INTERNAL_BASE_URL = env("AUTH_INTERNAL_BASE_URL", default="")
EVENTS_INTERNAL_BASE_URL = env("EVENTS_INTERNAL_BASE_URL", default="")
POSTS_INTERNAL_BASE_URL = env("POSTS_INTERNAL_BASE_URL", default="")

# 7-2. API Gateway auth handoff
GATEWAY_USER_ID_HEADER = env("GATEWAY_USER_ID_HEADER", default="X-User-Id")

# 9. 정적파일경로설정
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# 10. ALB사용 시 리다이렉션 오류 방지
# ALB가 전달해준 원래 호스트 정보를 신뢰합니다.
USE_X_FORWARDED_HOST = True

# 11. Notification pipeline
AWS_REGION = env("AWS_REGION", default=env("AWS_DEFAULT_REGION", default="ap-northeast-2"))

NOTIFICATION_EVENT_BUS_NAME = env("NOTIFICATION_EVENT_BUS_NAME", default="stagelog-notification-bus")
NOTIFICATION_SQS_QUEUE_URL = env("NOTIFICATION_SQS_QUEUE_URL", default="")
NOTIFICATION_DDB_TABLE_NAME = env("NOTIFICATION_DDB_TABLE_NAME", default="stagelog-notifications")
NOTIFICATION_CONSUMER_MAX_MESSAGES = env.int("NOTIFICATION_CONSUMER_MAX_MESSAGES", default=10)
NOTIFICATION_CONSUMER_WAIT_TIME_SECONDS = env.int("NOTIFICATION_CONSUMER_WAIT_TIME_SECONDS", default=20)
NOTIFICATION_DDB_TTL_DAYS = env.int("NOTIFICATION_DDB_TTL_DAYS", default=30)
NOTIFICATION_DEDUPE_TTL_SECONDS = env.int("NOTIFICATION_DEDUPE_TTL_SECONDS", default=86400)
NOTIFICATION_UNREAD_CACHE_TTL_SECONDS = env.int("NOTIFICATION_UNREAD_CACHE_TTL_SECONDS", default=3600)

# 12. Redis (ElastiCache)
REDIS_HOST = env("REDIS_HOST", default="")
REDIS_PORT = env.int("REDIS_PORT", default=6379)
REDIS_DB = env.int("REDIS_DB", default=0)
REDIS_PASSWORD = env("REDIS_PASSWORD", default="")
REDIS_SSL = env.bool("REDIS_SSL", default=False)

# 13. Auto Ban (IP filter)
AUTO_BAN_ENABLED = env.bool("AUTO_BAN_ENABLED", default=False)
AUTO_BAN_LIMIT_WINDOW_SECONDS = env.int("AUTO_BAN_LIMIT_WINDOW_SECONDS", default=60)
AUTO_BAN_MAX_REQUESTS = env.int("AUTO_BAN_MAX_REQUESTS", default=100)
AUTO_BAN_BLOCK_TIME_SECONDS = env.int("AUTO_BAN_BLOCK_TIME_SECONDS", default=3600)

# 14. Cache (Redis 공유 / 로컬 fallback)
if REDIS_HOST:
    redis_auth = ""
    if REDIS_PASSWORD:
        redis_auth = f":{REDIS_PASSWORD}@"
    redis_scheme = "rediss" if REDIS_SSL else "redis"
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": f"{redis_scheme}://{redis_auth}{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "unique-snowflake",
        }
    }
