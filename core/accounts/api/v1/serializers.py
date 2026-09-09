from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from accounts.models.users import User


class RegisterSerializer(serializers.ModelSerializer):
    """
    Registration input: email + password only. first_name/last_name
    are deliberately not accepted here (not requested for this
    endpoint), and email uniqueness is enforced automatically by
    ModelSerializer via the model's `unique=True` constraint.
    """
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ["id", "email", "password"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        # Goes through the custom UserManager so password hashing and
        # normalization happen the same way as createsuperuser/shell
        # user creation — no duplicate creation logic here.
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    """Safe, read-only representation of a User for API responses. No
    password field exists on it at all, so it can never be returned."""

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "created_at"]
        read_only_fields = fields