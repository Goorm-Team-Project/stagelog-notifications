import jwt
import datetime
import functools

from django.http import JsonResponse, HttpResponse
from django.conf import settings

def health_check(request):
    return HttpResponse("OK", status=200)

def common_response(success=True, data=None, message="", status=200):
    """
    API 공통 응답 함수
    :param success: 성공 여부 (True/False)
    :param data: 반환할 데이터 (Dictionary or List)
    :param message: 클라이언트에게 보낼 메시지
    :param status: HTTP 상태 코드
    """
    payload = {
        "success": success,
        "message": message,
        "data": data,
    }
    # status 코드는 HTTP 응답 헤더에 설정됨
    return JsonResponse(payload, status=status, json_dumps_params={'ensure_ascii': False})

# 2. 액세스 토큰 생성 함수
def create_access_token(user_id):
    """
    User ID를 받아 JWT 액세스 토큰을 생성
    """
    payload = {
        'user_id': user_id,
        # settings에 설정한 시간(예: 30분) 후 만료
        'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=settings.JWT_EXP_DELTA_SECONDS),
        'iat': datetime.datetime.utcnow(), # 발급 시간
    }
    
    # PyJWT encode
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token

def create_refresh_token(user_id):
    """
    Refresh Token 생성 (유효기간: 예시 2주)
    """
    payload = {
        'user_id': user_id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(weeks=2), # 2주
        'iat': datetime.datetime.utcnow(),
        'type': 'refresh' # 토큰 타입 명시
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token

# 회원가입용 임시 토큰 생성 함수
def create_register_token(provider, provider_id, email):
    payload = {
        "provider": provider,
        "provider_id": provider_id,
        "email": email,
        # 가입용은 짧게 (예: 10분)
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=10),
        "iat": datetime.datetime.utcnow()
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

# 3. 토큰 검증 함수 (데코레이터로 쓸 수도 있고 직접 호출도 가능)
def validate_token(token):
    """
    토큰을 받아 유효성을 검증하고, 유효하면 payload(user_id 포함)를 반환
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None  # 토큰 만료
    except jwt.InvalidTokenError:
        return None  # 위변조되거나 잘못된 토큰


def _auth_from_gateway(request):
    """
    API Gateway(Authorizer)에서 주입한 user id 헤더를 읽는다.
    - 헤더가 없으면 (None, None)
    - 헤더가 있지만 정수가 아니면 (None, error)
    - 유효하면 (user_id, None)
    """
    header_name = getattr(settings, "GATEWAY_USER_ID_HEADER", "X-User-Id")
    raw = request.headers.get(header_name)
    if raw is None:
        return None, None

    value = str(raw).strip()
    if not value:
        return None, "인증 사용자 정보가 비어 있습니다."

    try:
        return int(value), None
    except (TypeError, ValueError):
        return None, "인증 사용자 정보 형식이 잘못되었습니다."


def login_check(func):
    """
    API 뷰에 사용할 데코레이터
    """
    @functools.wraps(func)
    def wrapper(request, *args, **kwargs):
        user_id, error = _auth_from_gateway(request)
        if error:
            return common_response(success=False, message=error, status=401)
        if user_id is None:
            return common_response(success=False, message="인증 정보가 없습니다.", status=401)

        request.user_id = user_id
        return func(request, *args, **kwargs)
    
    return wrapper

# Optional Auth 헬퍼 추가
def get_optional_user_id(request):
    """
    Optional Auth (API Gateway 헤더 기반):
    - 헤더가 없으면 (None, None)
    - 헤더가 유효하면 (user_id, None)
    - 헤더가 잘못되면 (None, error)
    """
    user_id, error = _auth_from_gateway(request)
    if error:
        return None, error
    return user_id, None


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
