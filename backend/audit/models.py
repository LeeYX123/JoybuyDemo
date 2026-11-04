from django.db import models


class AuditLog(models.Model):
    actor = models.ForeignKey(
        "accounts_staff.StaffAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=100)
    request_id = models.UUIDField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    tenant_type = models.CharField(max_length=50, blank=True, default="")
    tenant_id = models.CharField(max_length=100, blank=True, default="")
    reason = models.CharField(max_length=500)
    before_state = models.JSONField(default=dict)
    after_state = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["action", "created_at"], name="audit_action_created_idx"),
            models.Index(
                fields=["target_type", "target_id", "created_at"],
                name="audit_target_created_idx",
            ),
        ]
