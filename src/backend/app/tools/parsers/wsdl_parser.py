"""WSDL / SOAP Specification Auto-Wrapping Parser.

Parses WSDL 1.1 / 2.0 XML specifications and converts SOAP operations into MCP Tool
definitions with automated SOAP Envelope serialization templates.
"""
import re
import xml.etree.ElementTree as ET
from typing import Any
from app.errors import AppError


def parse_wsdl_spec(raw_xml: str) -> list[dict[str, Any]]:
    """Parse WSDL XML and generate wrapped MCP Tool specifications."""
    if not raw_xml or ("<definitions" not in raw_xml and "<wsdl:definitions" not in raw_xml):
        raise AppError("WSDL_SPEC_INVALID", 422)

    try:
        # Strip XML namespaces and prefixes (e.g., <wsdl:operation> -> <operation>)
        clean_xml = re.sub(r' xmlns(:[a-zA-Z0-9_-]+)?="[^"]+"', "", raw_xml)
        clean_xml = re.sub(r'<(/?)[a-zA-Z0-9_-]+:', r"<\1", clean_xml)
        root = ET.fromstring(clean_xml)
    except Exception as err:
        raise AppError("WSDL_XML_PARSE_ERROR", 422) from err

    tools: list[dict[str, Any]] = []

    # Find portType and its operations
    port_types = root.findall(".//portType")
    target_ns = root.attrib.get("targetNamespace", "http://tempuri.org/")

    for pt in port_types:
        pt_name = pt.attrib.get("name", "SoapPort")
        for op in pt.findall("operation"):
            op_name = op.attrib.get("name")
            if not op_name:
                continue

            doc_node = op.find("documentation")
            doc_str = doc_node.text.strip() if doc_node is not None and doc_node.text else f"SOAP Operation {op_name}"

            # Input parameters from message/part elements
            input_node = op.find("input")
            msg_name = input_node.attrib.get("message", "").split(":")[-1] if input_node is not None else ""

            properties: dict[str, Any] = {}
            required: list[str] = []

            # Match corresponding message parts
            if msg_name:
                msg = root.find(f".//message[@name='{msg_name}']")
                if msg is not None:
                    for part in msg.findall("part"):
                        p_name = part.attrib.get("name")
                        p_type = part.attrib.get("type", "string").split(":")[-1]
                        if p_name:
                            properties[p_name] = {
                                "type": "string" if p_type in ["string", "dateTime", "date"] else "number" if p_type in ["int", "long", "float", "double"] else "string",
                                "description": f"SOAP parameter {p_name} ({p_type})"
                            }
                            required.append(p_name)

            if not properties:
                # Default generic request payload parameter if no specific parts found
                properties["request_payload"] = {
                    "type": "string",
                    "description": "Raw XML or JSON parameter mapping for the SOAP request"
                }

            soap_action = f"{target_ns.rstrip('/')}/{op_name}"
            description = (
                f"[SOAP / WSDL] {doc_str}\n"
                f"PortType: {pt_name}\n"
                f"Operation: {op_name}\n"
                f"SOAP Action: {soap_action}"
            )

            envelope_template = (
                f'<?xml version="1.0" encoding="utf-8"?>\n'
                f'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tns="{target_ns}">\n'
                f'  <soap:Header/>\n'
                f'  <soap:Body>\n'
                f'    <tns:{op_name}>\n'
                + "".join(f"      <tns:{p}>{{{p}}}</tns:{p}>\n" for p in properties)
                + f'    </tns:{op_name}>\n'
                f'  </soap:Body>\n'
                f'</soap:Envelope>'
            )

            tools.append({
                "tool_id": f"soap_{op_name.lower()}",
                "name": f"{op_name} (SOAP)",
                "description": description,
                "category": "api_soap",
                "source_type": "wsdl",
                "operation_name": op_name,
                "target_namespace": target_ns,
                "soap_action": soap_action,
                "envelope_template": envelope_template,
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                }
            })

    if not tools:
        raise AppError("NO_VALID_SOAP_OPERATIONS", 422)

    return tools
