"""Financial Packet / Message Layout Auto-Wrapping Parser.

Parses banking/financial message layouts (ISO 8583, EAI, FEP, TCP/Socket fixed-length
or delimited packet specifications) and generates MCP Tool schemas with automated
byte serialization (packing) and deserialization (unpacking).
"""
import re
from typing import Any
from app.errors import AppError


def parse_packet_spec(spec_data: dict[str, Any]) -> dict[str, Any]:
    """Parse financial packet layout and return wrapped MCP Tool specification."""
    packet_code = spec_data.get("packet_code", "").strip()
    if not packet_code or not re.match(r"^[a-zA-Z0-9_-]+$", packet_code):
        raise AppError("PACKET_CODE_INVALID", 422)

    packet_name = spec_data.get("packet_name", f"금융 전문 {packet_code}")
    protocol = spec_data.get("protocol", "tcp_socket").lower()
    fields = spec_data.get("fields", [])

    if not isinstance(fields, list) or not fields:
        raise AppError("PACKET_NO_FIELDS_SPECIFIED", 422)

    properties: dict[str, Any] = {}
    required: list[str] = []
    layout_meta: list[dict[str, Any]] = []
    total_length = 0

    for idx, field in enumerate(fields):
        if not isinstance(field, dict):
            continue
        f_id = field.get("field_id", "").strip()
        f_name = field.get("name", f_id).strip()
        f_type = field.get("type", "string").lower()  # 'string' or 'number'
        f_len = field.get("length", 10)
        f_pad = field.get("padding", "space" if f_type == "string" else "zero")
        is_req = field.get("required", True)

        if not f_id or not re.match(r"^[a-zA-Z0-9_]+$", f_id):
            continue

        total_length += int(f_len)
        properties[f_id] = {
            "type": "string" if f_type == "string" else "number",
            "description": f"[{f_len}바이트] {f_name} (패딩: {f_pad})"
        }
        if is_req:
            required.append(f_id)

        layout_meta.append({
            "order": idx,
            "field_id": f_id,
            "name": f_name,
            "type": f_type,
            "length": int(f_len),
            "padding": f_pad,
            "offset": total_length - int(f_len),
        })

    if not layout_meta:
        raise AppError("PACKET_FIELDS_INVALID", 422)

    tool_id = f"packet_{packet_code.lower()}"
    description = (
        f"[금융 전문 / {protocol.upper()}] {packet_name} (코드: {packet_code})\n"
        f"총 전문 길이: {total_length} Bytes, 필드 수: {len(layout_meta)}개\n"
        f"전송 규격: 고정길이 전문(ISO 8583 / EAI / FEP 표준 레이아웃)"
    )

    return {
        "tool_id": tool_id,
        "name": packet_name,
        "description": description,
        "category": "financial_packet",
        "source_type": "financial_packet",
        "packet_code": packet_code,
        "protocol": protocol,
        "total_length": total_length,
        "layout_meta": layout_meta,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
    }


def pack_financial_message(layout_meta: list[dict[str, Any]], values: dict[str, Any]) -> bytes:
    """Serialize dictionary values into fixed-length byte buffer based on layout."""
    buffer = bytearray()
    for field in sorted(layout_meta, key=lambda x: x["order"]):
        val = values.get(field["field_id"], "")
        f_type = field["type"]
        f_len = field["length"]
        f_pad = field["padding"]

        if f_type == "number":
            num_str = str(int(val)) if val != "" else "0"
            if len(num_str) > f_len:
                num_str = num_str[:f_len]
            # Left pad with zeroes
            padded = num_str.zfill(f_len)
        else:
            val_str = str(val) if val is not None else ""
            raw_bytes = val_str.encode("euc-kr", errors="replace")
            if len(raw_bytes) > f_len:
                raw_bytes = raw_bytes[:f_len]
            # Right pad with spaces
            pad_len = f_len - len(raw_bytes)
            padded_bytes = raw_bytes + b" " * pad_len
            buffer.extend(padded_bytes)
            continue

        buffer.extend(padded.encode("ascii"))
    return bytes(buffer)


def unpack_financial_message(layout_meta: list[dict[str, Any]], raw_bytes: bytes) -> dict[str, Any]:
    """Deserialize fixed-length byte buffer into dictionary."""
    result: dict[str, Any] = {}
    for field in sorted(layout_meta, key=lambda x: x["order"]):
        offset = field["offset"]
        length = field["length"]
        chunk = raw_bytes[offset:offset + length]
        if field["type"] == "number":
            try:
                result[field["field_id"]] = int(chunk.decode("ascii").strip() or 0)
            except ValueError:
                result[field["field_id"]] = 0
        else:
            result[field["field_id"]] = chunk.decode("euc-kr", errors="replace").strip()
    return result
