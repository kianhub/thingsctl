"""Errors safe to expose through CLI and plugin responses."""


class ThingsError(Exception):
    def __init__(self, code, message, details=None, uncertain=False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.uncertain = uncertain

    def as_dict(self):
        result = {"code": self.code, "message": self.message}
        if self.details is not None:
            result["details"] = self.details
        return result

