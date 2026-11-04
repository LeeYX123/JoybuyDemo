from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts_staff.normalization import normalize_staff_email


class StaffLoginSerializer(serializers.Serializer):
    # 登录只接受邮箱+密码；历史 TOTP 设备不再参与登录校验。
    email = serializers.CharField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    def validate_email(self, value):
        try:
            return normalize_staff_email(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc


class StaffRoleUpdateSerializer(serializers.Serializer):
    role_codes = serializers.ListField(
        child=serializers.RegexField(r"^[a-z][a-z0-9_.-]{1,63}$"),
        allow_empty=True,
        max_length=50,
    )
    reason = serializers.CharField(min_length=3, max_length=500, trim_whitespace=True)

    def validate_role_codes(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Role codes must be unique.")
        return value
