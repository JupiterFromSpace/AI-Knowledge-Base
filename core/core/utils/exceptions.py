"""
Global DRF exception handling.

Converts exceptions into the project's centralized response envelope
(see core.utils.responses.APIResponse). This module owns exception ->
HTTP-response translation only; it does not define the envelope shape
itself, and it has no authentication- or app-specific logic.

No project-level exception handler existed before this task, so this
is the minimal handler required to satisfy that contract for:
ValidationError, AuthenticationFailed, NotAuthenticated,
PermissionDenied, NotFound, MethodNotAllowed, Throttled, and
unexpected (non-DRF) errors.
"""
import logging

from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework import status
from rest_framework.views import exception_handler as drf_exception_handler

from core.utils.responses import APIResponse

logger = logging.getLogger("django")


DEFAULT_ERROR_MESSAGES = {
    status.HTTP_400_BAD_REQUEST: "Validation failed.",
    status.HTTP_401_UNAUTHORIZED: "Authentication credentials were not provided or are invalid.",
    status.HTTP_403_FORBIDDEN: "You do not have permission to perform this action.",
    status.HTTP_404_NOT_FOUND: "The requested resource was not found.",
    status.HTTP_405_METHOD_NOT_ALLOWED: "This method is not allowed on this endpoint.",
    status.HTTP_429_TOO_MANY_REQUESTS: "Too many requests. Please try again later.",
}


def custom_exception_handler(exc, context):
    """
    Project-wide DRF EXCEPTION_HANDLER (wired in settings.REST_FRAMEWORK).

    Delegates to DRF's default handler for anything it already knows
    how to translate into an HTTP response, then reshapes that
    response into the standard envelope. Anything DRF doesn't
    recognize (a raw exception from application code) is treated as
    an unexpected server error: logged server-side, and reported to
    the client as a safe, generic 500 — never a stack trace, database
    error, or other internal detail.
    """
    # Django's Http404 isn't a DRF exception by default, but DRF's
    # handler normalizes it if we pass it through as one.
    if isinstance(exc, Http404):
        exc = drf_exceptions.NotFound()

    response = drf_exception_handler(exc, context)

    if response is None:
        logger.exception("Unhandled exception in %s", context.get("view"), exc_info=exc)
        return APIResponse.error(
            errors=None,
            message="An unexpected error occurred.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    message = DEFAULT_ERROR_MESSAGES.get(response.status_code, "Request failed.")

    # ValidationError's `.detail` is field -> [messages]; other
    # exceptions carry a flat `detail`. Normalize both into `errors`.
    if isinstance(response.data, dict) and "detail" not in response.data:
        errors = response.data
    else:
        detail = response.data.get("detail", response.data) if isinstance(response.data, dict) else response.data
        errors = {"detail": detail}

    return APIResponse.error(errors=errors, message=message, status_code=response.status_code)