from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts_buyers.models import VerificationCode
from accounts_buyers.normalization import normalize_identifier, normalize_target


class VerificationCodeRequestSerializer(serializers.Serializer):
    channel = serializers.CharField(max_length=16)
    target = serializers.CharField(max_length=254)
    purpose = serializers.CharField(max_length=24, default="REGISTER")

    def validate(self, attrs):
        channel = attrs["channel"].strip().upper()
        purpose = attrs["purpose"].strip().upper()
        if channel not in VerificationCode.Channel.values:
            raise serializers.ValidationError({"channel": "Use email or phone."})
        if purpose != VerificationCode.Purpose.REGISTER:
            raise serializers.ValidationError({"purpose": "Only register is currently supported."})
        try:
            target = normalize_target(channel, attrs["target"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"target": exc.messages}) from exc
        attrs["channel"] = channel
        attrs["target"] = target
        attrs["purpose"] = purpose
        return attrs


class BuyerRegisterSerializer(VerificationCodeRequestSerializer):
    verification_code = serializers.RegexField(r"^\d{6}$")
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value


class BuyerLoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    def validate_identifier(self, value):
        try:
            field, normalized = normalize_identifier(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        self.context["identifier_field"] = field
        return normalized
