from django.db import models

class Notification(models.Model):
    notification_id = models.BigAutoField(primary_key=True)

    user_id = models.BigIntegerField()
    post_id = models.BigIntegerField(null=True, blank=True)
    event_id = models.BigIntegerField(null=True, blank=True)
    
    relate_url = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    class Type(models.TextChoices):
        COMMENT = 'comment', 'Comment'
        EVENT = 'event', 'Event'
        POST_LIKE = 'post_like', 'Postlike'
        POST_DISLIKE = 'post_dislike', 'Postdislike'
        NOTICE = 'notice', 'Notice'

    type = models.CharField(
        max_length=20,
        choices = Type.choices,
        default = Type.COMMENT
    )

    is_read = models.BooleanField(default=False)
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"Noti[{self.notification_id}] User[{self.user_id}] : {self.message}"
