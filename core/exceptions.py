from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        errors = response.data
        if isinstance(errors, list):
            message = errors[0] if errors else "An error occurred"
        elif isinstance(errors, dict):
            for field, value in errors.items():
                if isinstance(value, list) and value:
                    message = f"{field}: {value[0]}" if field != "non_field_errors" else str(value[0])
                    break
                elif isinstance(value, str):
                    message = f"{field}: {value}" if field != "non_field_errors" else value
                    break
            else:
                message = str(errors)
        else:
            message = str(errors)

        response.data = {
            "success": False,
            "message": str(message),
            "errors": errors,
            "status_code": response.status_code,
        }

    return response
