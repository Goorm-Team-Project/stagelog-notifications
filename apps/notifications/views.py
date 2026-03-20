from django.core.paginator import Paginator
from common.utils import common_response, login_check
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_safe, require_http_methods 

from . import store

@require_safe
@csrf_exempt
@login_check
def get_notification_list(request):
    try:
        user_id = request.user_id

        # 1. 입력값 검증
        try:
            page = int(request.GET.get("page") or 1)
            size = 20
        except ValueError:
            return common_response(success=False, message="page는 정수여야 합니다.", status=400)

        type_param = (request.GET.get('type') or "").strip()
        notifications = store.list_notifications(user_id, type_filter=type_param or None)

        paginator = Paginator(notifications, size)
        page_obj = paginator.get_page(page)

        data = {
            "notifications": [
                {
                    "notification_id": row["notification_id"],
                    "type": row["type"],
                    "message": row["message"],
                    "is_read": row["is_read"],
                    "created_at": row["created_at"],
                    "post_id": row["post_id"],
                    "event_id": row["event_id"],
                    "relate_url": row["relate_url"],
                }
                for row in page_obj.object_list
            ],
            "has_next": page_obj.has_next(),
            "total_count": paginator.count,
        }

        return common_response(success=True, data=data, message="알림 조회 성공", status=200)

    except Exception as e:
        print(f"에러 로그: {e}") 
        return common_response(success=False, message="서버 에러", status=500)

@require_safe
@csrf_exempt
@login_check
def get_unread_notification(request):
    try:
        user_id = request.user_id

        unread_count = store.unread_count(user_id)

        return common_response(success=True, message="체크 완료", data={
                "has_unread": unread_count > 0,
                "unread_count": unread_count
            },
            status=200
        )
    except Exception as e:
        return common_response(success=False, message="서버 에러", status=500)

@require_http_methods(["PATCH"])
@csrf_exempt
@login_check
def read_notification(request, notification_id):
    try:
        updated = store.mark_notification_read(request.user_id, notification_id)
        if not updated:
            return common_response(success=False, message="존재하지 않는 알림입니다.", status=404)

        return common_response(success=True, message="읽음 처리 완료", status=200)

    except Exception as e:
        return common_response(success=False, message="서버 에러", status=500)
