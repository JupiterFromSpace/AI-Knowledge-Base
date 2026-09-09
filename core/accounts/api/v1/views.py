from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.api.v1.serializers import RegisterSerializer, UserSerializer
from accounts.models.users import User
from core.utils.responses import APIResponse


class RegisterView(generics.CreateAPIView):
    """
    POST /api/v1/auth/register/ — create a new platform user.

    Validation errors (duplicate/invalid email, missing/weak password)
    are raised as a DRF ValidationError via `raise_exception=True` and
    handled by core.utils.exceptions.custom_exception_handler, so this
    view only needs to shape the success case.
    """
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return APIResponse.success(
            data=UserSerializer(user).data,
            message="User registered successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """
    POST /api/v1/auth/login/ — exchange (email, password) for a JWT
    access/refresh pair.

    SimpleJWT's TokenObtainPairSerializer already derives its input
    field name from `User.USERNAME_FIELD` ("email" here), so no
    custom serializer is needed. Invalid credentials already raise
    AuthenticationFailed, handled by the global exception handler;
    this view only wraps the success response in the standard envelope.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        return APIResponse.success(data=response.data, message="Login successful.")


class RefreshTokenView(TokenRefreshView):
    """POST /api/v1/auth/token/refresh/ — exchange a refresh token for a new access token."""
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        return APIResponse.success(data=response.data, message="Token refreshed successfully.")