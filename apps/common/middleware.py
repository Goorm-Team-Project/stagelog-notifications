import logging

from django.core.cache import cache

from common.utils import common_response, get_client_ip

logger = logging.getLogger(__name__)


class AutoBanMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

        # 원본 로직 유지 + 설정값으로 조정 가능
        from django.conf import settings

        self.enabled = getattr(settings, "AUTO_BAN_ENABLED", False)
        self.limit_window = getattr(settings, "AUTO_BAN_LIMIT_WINDOW_SECONDS", 60)
        self.max_requests = getattr(settings, "AUTO_BAN_MAX_REQUESTS", 100)
        self.block_time = getattr(settings, "AUTO_BAN_BLOCK_TIME_SECONDS", 3600)

    def __call__(self, request):
        if not self.enabled:
            return self.get_response(request)

        ip = get_client_ip(request)
        if not ip:
            return self.get_response(request)

        if cache.get(f"block_{ip}"):
            logger.warning("차단된 IP 입니다: %s", ip)
            return common_response(success=False, message="차단된 IP 입니다.", status=403)

        request_key = f"req_count_{ip}"

        current_count = cache.get_or_set(request_key, 0, timeout=self.limit_window)
        try:
            cache.incr(request_key)
        except ValueError:
            # 키가 증발한 경우 재설정 후 증가
            cache.set(request_key, 1, timeout=self.limit_window)
            current_count = 0

        if int(current_count) >= self.max_requests:
            cache.set(f"block_{ip}", "banned", timeout=self.block_time)
            logger.error("자동으로 IP가 밴 되었습니다: %s. (Too many requests)", ip)
            return common_response(success=False, message="너무 많은 요청으로 차단되었습니다.", status=429)

        return self.get_response(request)
