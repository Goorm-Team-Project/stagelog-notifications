# notifications-service

## Responsibility
- Notification query API and notification consumer worker.
- API and consumer are in the same repository, deployed as separate workloads.

## Owned Domain
- Notification read/query model (DynamoDB)
- Notification consume pipeline from SQS

## API Scope
- Public: `/api/notifications*`

## Data Ownership
- DynamoDB table: `stagelog-notifications`
- Notification read model cache in Redis

## Dependencies
- Consumes SQS messages published by outbox-worker
- Uses shared notification event contract

## Runtime
- Deployment A: notifications API
- Deployment B: notification consumer worker (`consume_notification_queue`)
