"""Mock Financial Sandbox Servers for E2E Connector Verification.

Pure asyncio loopback servers for:
1. TLS TCP socket server for Fixed-length Financial Packets (80-byte layouts with LRC).
2. HTTPS server for OpenAPI endpoints (1 MiB overflow, latency timeout, 503 errors).
3. HTTPS server for SOAP/WSDL envelopes (SOAP 1.1/1.2, SOAP Fault).
"""
from __future__ import annotations

import asyncio
import datetime
import ipaddress
import json
import ssl
import tempfile
from typing import Any
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def generate_self_signed_cert() -> tuple[str, str]:
    """Generate temporary self-signed certificate and private key files for TLS testing."""
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "KR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VectorMoon Test Bank"),
        x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_file = tempfile.NamedTemporaryFile(delete=False, suffix=".crt")
    key_file = tempfile.NamedTemporaryFile(delete=False, suffix=".key")

    cert_file.write(cert.public_bytes(serialization.Encoding.PEM))
    cert_file.flush()
    key_file.write(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_file.flush()
    return cert_file.name, key_file.name


class FinancialPacketSandboxServer:
    """Mock TCP/TLS server handling 80-byte banking packets with LRC checksums."""

    def __init__(self, cert_path: str, key_path: str, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port
        self.cert_path = cert_path
        self.key_path = key_path
        self._server: asyncio.Server | None = None
        self.actual_port: int = 0

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await reader.readexactly(80)
            if len(data) != 80:
                writer.close()
                await writer.wait_closed()
                return

            body = data[:79]
            received_lrc = data[79]
            calculated_lrc = 0
            for b in body:
                calculated_lrc ^= b

            if received_lrc != calculated_lrc:
                res_code = b"9998"
            else:
                trx_type = data[10:14].decode("ascii", errors="replace")
                if trx_type == "ERR0":
                    res_code = b"9999"
                else:
                    res_code = b"0000"

            res_body = bytearray(data)
            res_body[14:18] = res_code
            res_lrc = 0
            for b in res_body[:79]:
                res_lrc ^= b
            res_body[79] = res_lrc

            writer.write(bytes(res_body))
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self) -> int:
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(certfile=self.cert_path, keyfile=self.key_path)

        self._server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port,
            ssl=ssl_ctx,
        )
        self.actual_port = self._server.sockets[0].getsockname()[1]
        return self.actual_port

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()


class HttpSandboxServer:
    """Mock HTTPS server handling OpenAPI & SOAP endpoints over pure asyncio streams."""

    def __init__(self, cert_path: str, key_path: str, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port
        self.cert_path = cert_path
        self.key_path = key_path
        self._server: asyncio.Server | None = None
        self.actual_port: int = 0

    async def _handle_http(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await reader.readline()
            if not line:
                return
            request_line = line.decode("iso-8859-1").strip()
            parts = request_line.split()
            if len(parts) < 2:
                return
            method, path = parts[0], parts[1]

            headers: dict[str, str] = {}
            while True:
                h_line = await reader.readline()
                if not h_line or h_line in (b"\r\n", b"\n"):
                    break
                decoded_h = h_line.decode("iso-8859-1").strip()
                if ":" in decoded_h:
                    hk, _, hv = decoded_h.partition(":")
                    headers[hk.strip().lower()] = hv.strip()

            content_length = int(headers.get("content-length", 0))
            body = b""
            if content_length > 0:
                body = await reader.readexactly(content_length)

            # Route handling
            if path == "/api/v1/delayed":
                await asyncio.sleep(2.0)
                resp_payload = b'{"status":"delayed_done"}'
                resp = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: " + str(len(resp_payload)).encode() + b"\r\n\r\n" + resp_payload
                )
                writer.write(resp)
                await writer.drain()

            elif path == "/api/v1/failing":
                resp_payload = b'{"error":"BANK_CORE_UNAVAILABLE"}'
                resp = (
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: " + str(len(resp_payload)).encode() + b"\r\n\r\n" + resp_payload
                )
                writer.write(resp)
                await writer.drain()

            elif path == "/api/v1/large-data":
                # Send 1.2 MiB chunked
                resp_hdr = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/octet-stream\r\n"
                    b"Transfer-Encoding: chunked\r\n\r\n"
                )
                writer.write(resp_hdr)
                await writer.drain()
                chunk = b"A" * 65536
                chunk_hdr = f"{len(chunk):X}\r\n".encode("ascii")
                for _ in range(20):
                    writer.write(chunk_hdr + chunk + b"\r\n")
                    await writer.drain()
                writer.write(b"0\r\n\r\n")
                await writer.drain()

            elif path.startswith("/api/v1/accounts/") and path.endswith("/balance"):
                auth = headers.get("authorization", "")
                if not auth.startswith("Bearer "):
                    resp_payload = b'{"error":"UNAUTHORIZED"}'
                    resp = (
                        b"HTTP/1.1 401 Unauthorized\r\n"
                        b"Content-Type: application/json\r\n"
                        b"Content-Length: " + str(len(resp_payload)).encode() + b"\r\n\r\n" + resp_payload
                    )
                else:
                    account_id = path.split("/")[4]
                    resp_dict = {
                        "account_id": account_id,
                        "currency": "KRW",
                        "available_balance": 15000000,
                        "status": "ACTIVE",
                    }
                    resp_payload = json.dumps(resp_dict).encode("utf-8")
                    resp = (
                        b"HTTP/1.1 200 OK\r\n"
                        b"Content-Type: application/json\r\n"
                        b"Content-Length: " + str(len(resp_payload)).encode() + b"\r\n\r\n" + resp_payload
                    )
                writer.write(resp)
                await writer.drain()

            elif path == "/soap/AccountService":
                body_str = body.decode("utf-8", errors="replace")
                soap_action = headers.get("soapaction", "").strip('"')
                if "<!DOCTYPE" in body_str or "<!ENTITY" in body_str:
                    resp_xml = (
                        b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
                        b'<soap:Body><soap:Fault><faultcode>soap:Client</faultcode>'
                        b'<faultstring>XXE_FORBIDDEN</faultstring></soap:Fault></soap:Body></soap:Envelope>'
                    )
                    resp = (
                        b"HTTP/1.1 400 Bad Request\r\n"
                        b"Content-Type: text/xml; charset=utf-8\r\n"
                        b"Content-Length: " + str(len(resp_xml)).encode() + b"\r\n\r\n" + resp_xml
                    )
                elif "GetAccountBalance" in soap_action or "GetAccountBalance" in body_str:
                    resp_xml = (
                        b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
                        b'<soap:Body>'
                        b'<GetAccountBalanceResponse xmlns="http://bank.example.com/account">'
                        b'<Balance>25000000</Balance>'
                        b'<Currency>KRW</Currency>'
                        b'<Status>NORMAL</Status>'
                        b'</GetAccountBalanceResponse>'
                        b'</soap:Body></soap:Envelope>'
                    )
                    resp = (
                        b"HTTP/1.1 200 OK\r\n"
                        b"Content-Type: text/xml; charset=utf-8\r\n"
                        b"Content-Length: " + str(len(resp_xml)).encode() + b"\r\n\r\n" + resp_xml
                    )
                else:
                    resp_xml = (
                        b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
                        b'<soap:Body><soap:Fault><faultcode>soap:Client</faultcode>'
                        b'<faultstring>ACTION_UNKNOWN</faultstring></soap:Fault></soap:Body></soap:Envelope>'
                    )
                    resp = (
                        b"HTTP/1.1 404 Not Found\r\n"
                        b"Content-Type: text/xml; charset=utf-8\r\n"
                        b"Content-Length: " + str(len(resp_xml)).encode() + b"\r\n\r\n" + resp_xml
                    )
                writer.write(resp)
                await writer.drain()

            else:
                resp = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
                writer.write(resp)
                await writer.drain()

        except Exception:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self) -> int:
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(certfile=self.cert_path, keyfile=self.key_path)

        self._server = await asyncio.start_server(
            self._handle_http,
            self.host,
            self.port,
            ssl=ssl_ctx,
        )
        self.actual_port = self._server.sockets[0].getsockname()[1]
        return self.actual_port

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
