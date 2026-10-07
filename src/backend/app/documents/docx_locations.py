"""Validate immutable DOCX codepoint maps independent of XML/filesystem access."""
def validate_docx_locations(locations, character_length):
    if type(locations) is not list or not 1 <= len(locations) <= 2000:
        raise ValueError("DOCX_LOCATION_INVALID")
    previous = -2
    seen = set()
    for item in locations:
        if type(item) is not dict or item.get("kind") not in ("paragraph", "table_cell"):
            raise ValueError("DOCX_LOCATION_INVALID")
        fields = ("paragraph",) if item["kind"] == "paragraph" else ("table", "row", "column")
        if set(item) != {"kind", "start", "end", *fields}:
            raise ValueError("DOCX_LOCATION_INVALID")
        if any(type(item[k]) is not int for k in ("start", "end", *fields)):
            raise ValueError("DOCX_LOCATION_INVALID")
        identity = (item["kind"], *(item[k] for k in fields))
        if identity in seen or any(not 1 <= item[k] <= 20000 for k in fields):
            raise ValueError("DOCX_LOCATION_INVALID")
        if item["start"] != previous + 2 or not item["start"] < item["end"] <= character_length:
            raise ValueError("DOCX_LOCATION_INVALID")
        seen.add(identity)
        previous = item["end"]
    if previous != character_length:
        raise ValueError("DOCX_LOCATION_INVALID")
