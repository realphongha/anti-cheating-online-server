import re

EMAIL_REGEX = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"


def validate_email(string):
    return re.fullmatch(EMAIL_REGEX, string)
    