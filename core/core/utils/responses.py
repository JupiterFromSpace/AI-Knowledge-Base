"""
Centralized API response envelope for the project.

Every API endpoint, in every app, should return a response shaped like:

    {"success": true,  "message": "...", "data": {...}, "errors": null}
    {"success": false, "message": "...", "data": null,  "errors": {...}}

This module only knows how to build that envelope. It has no
knowledge of authentication, validation rules, or any other
application logic — views call `APIResponse.success(...)` /
`APIResponse.error(...)` with whatever message/data/errors are
relevant to them, and `core.utils.exceptions.custom_exception_handler`
uses `APIResponse.error(...)` to convert raised exceptions into the
same envelope automatically.
"""
from rest_framework import status
from rest_framework.response import Response


class APIResponse:
    """Reusable success/error envelope builders. Not a base view class
    or mixin on purpose — call these directly from any view, in any
    app, so every endpoint stays consistent without extra coupling."""

    @staticmethod
    def success(data=None, message="Operation completed successfully.", status_code=status.HTTP_200_OK):
        return Response(
            {"success": True, "message": message, "data": data, "errors": None},
            status=status_code,
        )

    @staticmethod
    def error(errors=None, message="Request failed.", status_code=status.HTTP_400_BAD_REQUEST):
        return Response(
            {"success": False, "message": message, "data": None, "errors": errors},
            status=status_code,
        )