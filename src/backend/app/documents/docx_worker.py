"""Isolated OOXML reader. Bounded in-memory ZIP/XML; no project imports."""
import io
import json
import logging
import posixpath
import re
import resource
import stat
import sys
import zipfile
resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
from defusedxml import ElementTree as XML
from defusedxml.common import DefusedXmlException
logging.disable(logging.CRITICAL)
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
WORD_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml."
TYPES = {
    "word/document.xml": WORD_TYPE + "document.main+xml",
    "word/styles.xml": WORD_TYPE + "styles+xml",
    "word/stylesWithEffects.xml": "application/vnd.ms-word.stylesWithEffects+xml",
    "word/settings.xml": WORD_TYPE + "settings+xml",
    "word/fontTable.xml": WORD_TYPE + "fontTable+xml",
    "word/webSettings.xml": WORD_TYPE + "webSettings+xml",
    "word/numbering.xml": WORD_TYPE + "numbering+xml",
    "word/theme/theme1.xml": "application/vnd.openxmlformats-officedocument.theme+xml",
    "docProps/core.xml": "application/vnd.openxmlformats-package.core-properties+xml",
    "docProps/app.xml": "application/vnd.openxmlformats-officedocument.extended-properties+xml",
    "docProps/custom.xml": "application/vnd.openxmlformats-officedocument.custom-properties+xml",
}
ALLOWED = set(TYPES) | {"[Content_Types].xml", "_rels/.rels", "word/_rels/document.xml.rels"}
ROOT_REL = {
    OFFICE + "officeDocument": "word/document.xml",
    REL + "/metadata/core-properties": "docProps/core.xml",
    OFFICE + "extended-properties": "docProps/app.xml",
    OFFICE + "custom-properties": "docProps/custom.xml",
}
BODY_REL = {OFFICE + k: "word/" + k + ".xml" for k in ("styles", "settings", "fontTable", "webSettings", "numbering")}
BODY_REL[OFFICE + "theme"] = "word/theme/theme1.xml"
BODY_REL["http://schemas.microsoft.com/office/2007/relationships/stylesWithEffects"] = "word/stylesWithEffects.xml"
FORBIDDEN = {"ins", "del", "moveFrom", "moveTo", "drawing", "pict", "object", "hyperlink", "fldSimple", "fldChar", "instrText", "sdt", "altChunk", "txbxContent", "footnoteReference", "endnoteReference", "commentRangeStart", "commentRangeEnd", "commentReference", "numPr", "gridSpan", "vMerge", "hMerge", "vanish", "webHidden", "sym", "subDoc", "gridBefore", "gridAfter"}

def fail(code):
    raise ValueError(code)

def extract(raw):
    if not raw.startswith(b"PK\x03\x04") or not 1 <= len(raw) <= 131072:
        fail("DOCX_INVALID")
    parts = {}
    total = 0
    directories = {p[:i+1] for p in ALLOWED for i,c in enumerate(p) if c == "/"}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        items = archive.infolist()
        if not 1 <= len(items) <= 200:
            fail("DOCX_ZIP_LIMIT")
        seen = set()
        for item in items:
            name = item.filename
            if name in seen or name.startswith("/") or "\\" in name or ".." in name.split("/") or item.orig_filename != name or stat.S_IFMT(item.external_attr >> 16) not in (0, stat.S_IFREG, stat.S_IFDIR):
                fail("DOCX_INVALID")
            seen.add(name)
            if item.flag_bits & 1:
                fail("DOCX_ENCRYPTED")
            if item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                fail("DOCX_INVALID")
            if item.is_dir():
                if name not in directories or item.file_size:
                    fail("DOCX_INVALID")
                continue
            if name not in ALLOWED:
                fail("DOCX_UNSUPPORTED")
            if item.file_size > 1048576 or item.file_size > max(1, item.compress_size)*100:
                fail("DOCX_ZIP_LIMIT")
            total += item.file_size
            if total > 4194304:
                fail("DOCX_ZIP_LIMIT")
            with archive.open(item) as stream:
                content = stream.read(1048577)
            if len(content) != item.file_size or len(content) > 1048576:
                fail("DOCX_ZIP_LIMIT")
            parts[name] = content
    if not {"[Content_Types].xml", "_rels/.rels", "word/document.xml"} <= parts.keys():
        fail("DOCX_INVALID")
    nodes = 0
    def xml(content):
        nonlocal nodes
        decoded = content.decode("utf-8-sig")
        if re.search(r"<\?(?!xml(?:\s|\?>))", decoded):
            fail("DOCX_ACTIVE_CONTENT")
        depth = 0
        parser = XML.iterparse(io.BytesIO(content), events=("start", "end"), forbid_dtd=True, forbid_entities=True, forbid_external=True)
        for event, element in parser:
            if event == "start":
                depth += 1
                nodes += 1
                if depth > 50 or nodes > 20000:
                    fail("DOCX_XML_LIMIT")
            else:
                depth -= 1
        return parser.root
    roots = {name: xml(content) for name, content in parts.items()}
    types = roots["[Content_Types].xml"]
    if types.tag != "{"+CT+"}Types":
        fail("DOCX_INVALID")
    defaults = {}; overrides = {}
    for entry in types:
        if entry.tag == "{"+CT+"}Default":
            if set(entry.attrib) != {"Extension", "ContentType"}:
                fail("DOCX_INVALID")
            ext = entry.get("Extension"); value = entry.get("ContentType")
            expected = {"xml": "application/xml", "rels": "application/vnd.openxmlformats-package.relationships+xml"}
            if ext in defaults or expected.get(ext) != value:
                fail("DOCX_UNSUPPORTED")
            defaults[ext] = value
        elif entry.tag == "{"+CT+"}Override":
            if set(entry.attrib) != {"PartName", "ContentType"}:
                fail("DOCX_INVALID")
            name = entry.get("PartName"); value = entry.get("ContentType")
            if not name.startswith("/") or name in overrides or name[1:] not in parts or TYPES.get(name[1:]) != value:
                fail("DOCX_UNSUPPORTED")
            overrides[name] = value
        else:
            fail("DOCX_INVALID")
    if overrides.get("/word/document.xml") != TYPES["word/document.xml"] or defaults.get("rels") != "application/vnd.openxmlformats-package.relationships+xml":
        fail("DOCX_INVALID")
    for name in set(TYPES) & parts.keys():
        if overrides.get("/"+name) != TYPES[name]:
            fail("DOCX_INVALID")
    def relations(name, allowed, base):
        root = roots.get(name)
        if root is None:
            return
        if root.tag != "{"+REL+"}Relationships":
            fail("DOCX_INVALID")
        ids = set(); main = 0
        for rel in root:
            if rel.tag != "{"+REL+"}Relationship" or set(rel.attrib) - {"Id", "Type", "Target", "TargetMode"} or not {"Id", "Type", "Target"} <= rel.attrib.keys():
                fail("DOCX_INVALID")
            if rel.get("TargetMode", "Internal") != "Internal":
                fail("DOCX_ACTIVE_CONTENT")
            rid = rel.get("Id"); target = rel.get("Target"); kind = rel.get("Type")
            if not rid or rid in ids or target.startswith("/") or "\\" in target or ".." in target.split("/") or ":" in target or "#" in target:
                fail("DOCX_INVALID")
            ids.add(rid)
            resolved = posixpath.join(base, target)
            if allowed.get(kind) != resolved or resolved not in parts:
                fail("DOCX_ACTIVE_CONTENT")
            if kind == OFFICE + "officeDocument":
                main += 1
        if not base and main != 1:
            fail("DOCX_INVALID")
    relations("_rels/.rels", ROOT_REL, "")
    relations("word/_rels/document.xml.rels", BODY_REL, "word")
    document = roots["word/document.xml"]
    if document.tag != "{"+W+"}document" or len(document) != 1 or document[0].tag != "{"+W+"}body":
        fail("DOCX_UNSUPPORTED")
    for element in document.iter():
        if not element.tag.startswith("{"+W+"}") or element.tag.split("}")[-1] in FORBIDDEN:
            fail("DOCX_UNSUPPORTED")
        if element.tag != "{"+W+"}t" and (element.text or "").strip() or (element.tail or "").strip():
            fail("DOCX_UNSUPPORTED")
        if element.tag in {"{"+W+"}"+x for x in ("pPr", "rPr", "tblPr", "tblGrid", "trPr", "tcPr", "sectPr")}:
            if any(x.tag in {"{"+W+"}"+k for k in ("t", "p", "r", "tbl", "tc", "tr")} for x in list(element.iter())[1:]):
                fail("DOCX_UNSUPPORTED")
    def local(element):
        return element.tag.split("}")[-1]
    def paragraph(element):
        chunks = []
        for child in element:
            if local(child) == "pPr":
                continue
            if local(child) != "r":
                fail("DOCX_UNSUPPORTED")
            for token in child:
                tag = local(token)
                if tag == "rPr":
                    continue
                if tag == "t" and not len(token):
                    chunks.append(token.text or "")
                elif tag == "tab" and not len(token):
                    chunks.append("\t")
                elif tag in ("br", "cr") and not len(token):
                    chunks.append("\n")
                else:
                    fail("DOCX_UNSUPPORTED")
        return "".join(chunks)
    values = []; locations = []; offset = 0
    def add(text, locator):
        nonlocal offset
        if not text.strip():
            return
        if "\x00" in text:
            fail("DOCX_INVALID")
        if values:
            values.append("\n\n"); offset += 2
        start = offset; values.append(text); offset += len(text)
        if offset > 40000 or len(locations) >= 2000:
            fail("DOCX_TEXT_LIMIT")
        locations.append(dict(locator, start=start, end=offset))
    paragraph_no = 0; table_no = 0; section_seen = False
    for child in document[0]:
        tag = local(child)
        if section_seen:
            fail("DOCX_UNSUPPORTED")
        if tag == "sectPr":
            section_seen = True
        elif tag == "p":
            paragraph_no += 1
            add(paragraph(child), {"kind": "paragraph", "paragraph": paragraph_no})
        elif tag == "tbl":
            table_no += 1; row_no = 0
            for row in child:
                if local(row) in ("tblPr", "tblGrid"):
                    continue
                if local(row) != "tr":
                    fail("DOCX_UNSUPPORTED")
                row_no += 1; col_no = 0
                for cell in row:
                    if local(cell) == "trPr":
                        continue
                    if local(cell) != "tc":
                        fail("DOCX_UNSUPPORTED")
                    col_no += 1; cell_text = []
                    for item in cell:
                        if local(item) == "tcPr":
                            continue
                        if local(item) != "p":
                            fail("DOCX_UNSUPPORTED")
                        cell_text.append(paragraph(item))
                    add("\n".join(cell_text), {"kind": "table_cell", "table": table_no, "row": row_no, "column": col_no})
        else:
            fail("DOCX_UNSUPPORTED")
    text = "".join(values)
    if not locations:
        fail("DOCX_EMPTY")
    if len(text.encode()) > 131072:
        fail("DOCX_TEXT_LIMIT")
    return {"text": text, "locations": locations, "parser_version": "docx-v1+defusedxml-0.7.1"}
try:
    result = extract(sys.stdin.buffer.read(131073))
except DefusedXmlException:
    result = {"error": "DOCX_ACTIVE_CONTENT"}
except ValueError as error:
    safe = {"DOCX_INVALID", "DOCX_UNSUPPORTED", "DOCX_ENCRYPTED", "DOCX_ZIP_LIMIT", "DOCX_XML_LIMIT", "DOCX_TEXT_LIMIT", "DOCX_EMPTY", "DOCX_ACTIVE_CONTENT"}
    result = {"error": str(error) if str(error) in safe else "DOCX_INVALID"}
except Exception:
    result = {"error": "DOCX_INVALID"}
sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
