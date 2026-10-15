"""Review comments are mandatory on every new administrative decision."""
from typing import Annotated
from pydantic import StrictStr,AfterValidator

def clean_comment(value):
    value=value.strip()
    if not 1<=len(value)<=500 or '\x00' in value:raise ValueError('REVIEW_COMMENT_INVALID')
    try:value.encode('utf-8')
    except UnicodeError:raise ValueError('REVIEW_COMMENT_INVALID') from None
    return value
ReviewComment=Annotated[StrictStr,AfterValidator(clean_comment)]
