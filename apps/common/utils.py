import functools

from django.http import JsonResponse, HttpResponse

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
