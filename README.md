# Notifications Service

`notifications`는 알림 조회 API와 SQS consumer를 함께 포함한 서비스입니다.

## Responsibility
- 사용자 알림 목록/읽음 상태 조회
- 알림 읽음 처리
- SQS 메시지를 소비해 DynamoDB read model 적재

## Main Routes
- Public
  - `/api/notifications*`

## Runtime
- API와 consumer가 같은 이미지를 공유합니다
- API는 Gunicorn으로 실행되고, consumer는 별도 command로 큐를 소비합니다
- MariaDB 없이 DynamoDB, SQS, Redis 중심으로 동작합니다

## Pipeline
알림 적재 흐름은 아래와 같습니다.

1. `posts`, `auth`, `events` 서비스가 outbox row를 생성합니다.
2. `outbox-worker`가 outbox row를 읽어 EventBridge bus에 publish 합니다.
3. EventBridge rule이 알림 이벤트를 notifications SQS queue로 전달합니다.
4. `notifications-consumer`가 SQS 메시지를 받아 DynamoDB read model을 갱신합니다.
5. `notifications-api`가 DynamoDB에서 사용자 알림 목록과 unread 상태를 조회합니다.

핵심 AWS 리소스는 아래와 같습니다.
- EventBridge bus: `stagelog-notification-bus`
- SQS queue: notifications queue / DLQ
- DynamoDB table: `stagelog-notifications`

현재 read model 저장 방식은 원본 `stagelog-backend-migration`과 맞춰져 있습니다.
- 알림 row PK: 사용자 기준 partition key
- 알림 row SK: `NOTI#{notification_id}`
- unread count row SK: `META#COUNTS`
- 읽음 처리 시 `is_read` 갱신과 `META#COUNTS.unread_count` 감소를 함께 수행합니다

## Deploy
- Kubernetes 매니페스트
  - [`notifications/deploy/k8s/notifications-env-externalsecret.yaml`](/home/woosupar/stagelog/notifications/deploy/k8s/notifications-env-externalsecret.yaml)
  - [`notifications/deploy/k8s/notifications-api-serviceaccount.yaml`](/home/woosupar/stagelog/notifications/deploy/k8s/notifications-api-serviceaccount.yaml)
  - [`notifications/deploy/k8s/notifications-api-deployment.yaml`](/home/woosupar/stagelog/notifications/deploy/k8s/notifications-api-deployment.yaml)
  - [`notifications/deploy/k8s/notifications-consumer-serviceaccount.yaml`](/home/woosupar/stagelog/notifications/deploy/k8s/notifications-consumer-serviceaccount.yaml)
  - [`notifications/deploy/k8s/notifications-consumer-deployment.yaml`](/home/woosupar/stagelog/notifications/deploy/k8s/notifications-consumer-deployment.yaml)
  - [`notifications/deploy/k8s/notifications-consumer-scaledobject.yaml`](/home/woosupar/stagelog/notifications/deploy/k8s/notifications-consumer-scaledobject.yaml)
- CI/CD workflow
  - [`notifications/.github/workflows/build-and-push.yml`](/home/woosupar/stagelog/notifications/.github/workflows/build-and-push.yml)

배포 흐름은 아래와 같습니다.
- GitHub Actions가 이미지를 빌드해 ECR에 push
- 같은 workflow가 `stagelog-gitops`의 API/consumer 이미지 태그를 함께 갱신
- ArgoCD가 변경된 태그를 감지해 클러스터에 반영

## Configuration
주요 환경변수 예시는 [`notifications/.env.example`](/home/woosupar/stagelog/notifications/.env.example) 에 있습니다.

운영 환경에서는 SSM Parameter Store를 소스 오브 트루스로 사용하고, ExternalSecret이 필요한 키만 Kubernetes Secret으로 동기화합니다.

## Notes
- 알림 조회 모델은 DynamoDB의 `stagelog-notifications` 테이블을 사용합니다.
- 읽음 처리 모델은 원본 `stagelog-backend-migration`의 `notification_id` 및 `META#COUNTS` 구조와 맞춰져 있습니다.
- API와 consumer는 각각 다른 IRSA role을 사용합니다.
- consumer가 실제로 적재를 수행하려면 SQS consume 권한과 DynamoDB write 권한이 모두 필요합니다.
- API가 목록/읽음 처리를 수행하려면 DynamoDB `Query`, `GetItem`, `UpdateItem` 권한이 필요합니다.
