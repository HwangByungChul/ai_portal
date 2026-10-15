"""Bounded single-pass prompt binding. Never eval expressions or rebind values."""
import re
from app.errors import AppError

TOKEN = re.compile(r'\{\{([A-Za-z][A-Za-z0-9_]{0,39})\}\}')


def compile_template(template: str, values: dict[str, str]) -> tuple[list[str], str]:
    def reject():
        raise AppError('BUILDER_TEMPLATE_INVALID', 422)
    if not isinstance(template, str) or not template.strip() or len(template) > 2000:
        reject()
    remainder = TOKEN.sub('', template)
    if '{{' in remainder or '}}' in remainder:
        reject()
    names = sorted(set(TOKEN.findall(template)))
    if len(names) > 20 or type(values) is not dict or set(values) != set(names):
        reject()
    for value in values.values():
        if type(value) is not str or not value.strip() or len(value) > 2000:
            reject()
    result = TOKEN.sub(lambda match: values[match[1]], template)
    try:
        if '\x00' in result or len(result) > 8000 or len(result.encode('utf-8')) > 24000:
            reject()
    except UnicodeError:
        reject()
    return names, result
