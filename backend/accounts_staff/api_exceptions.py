from rest_framework.exceptions import APIException


class StaffApiError(APIException):
    def __init__(self, *, business_code: str, message: str, status_code: int):
        self.business_code = business_code
        self.status_code = status_code
        super().__init__(detail=message, code=business_code.lower())
