"""Trusted XLSX boundary; reuse the verified local isolation/resource runner."""
import json
from pathlib import Path
from app.errors import AppError
from app.documents.pdf import sandbox_command, run_isolated
from app.documents.xlsx_locations import validate_xlsx_locations
from app.documents.formats import XLSX_PARSER_VERSION

ERRORS = {"XLSX_INVALID", "XLSX_UNSUPPORTED", "XLSX_ENCRYPTED", "XLSX_ZIP_LIMIT", "XLSX_XML_LIMIT", "XLSX_TEXT_LIMIT", "XLSX_EMPTY", "XLSX_SHEET_LIMIT", "XLSX_ACTIVE_CONTENT"}

def extract_xlsx(content):
    if type(content) is not bytes or not 1 <= len(content) <= 131072 or not content.startswith(b"PK\x03\x04"):
        raise AppError("XLSX_INVALID", 422)
    try:
        result = run_isolated(sandbox_command(Path(__file__).with_name("xlsx_worker.py")), content)
    except AppError as error:
        code = "XLSX_RESOURCE_LIMIT" if error.code == "PDF_RESOURCE_LIMIT" else "XLSX_PARSER_UNAVAILABLE"
        raise AppError(code, 422 if code == "XLSX_RESOURCE_LIMIT" else 503) from None
    except OSError:
        raise AppError("XLSX_PARSER_UNAVAILABLE", 503) from None
    if result.returncode != 0:
        raise AppError("XLSX_RESOURCE_LIMIT" if result.returncode < 0 else "XLSX_PARSER_UNAVAILABLE", 422 if result.returncode < 0 else 503)
    if len(result.stdout) > 1048576:
        raise AppError("XLSX_RESOURCE_LIMIT", 422)
    try:
        value = json.loads(result.stdout)
        if type(value) is dict and set(value) == {"error"} and value["error"] in ERRORS:
            raise AppError(value["error"], 422)
        if type(value) is not dict or set(value) != {"text", "locations", "parser_version"} or value["parser_version"] != XLSX_PARSER_VERSION or type(value["text"]) is not str or not value["text"].strip() or "\x00" in value["text"] or not 1 <= len(value["text"]) <= 40000 or len(value["text"].encode()) > 131072:
            raise ValueError()
        validate_xlsx_locations(value["locations"], len(value["text"]))
        return value
    except (ValueError, TypeError, KeyError):
        raise AppError("XLSX_PARSER_UNAVAILABLE", 503) from None
