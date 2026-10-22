"""Authenticated repository boundary for verified IdP subject mappings."""
import psycopg
from app.db import tenant_transaction
from app.errors import AppError


class SubjectMappingRepository:
    def __init__(self, pool):
        self.pool = pool

    async def control(self, ctx, action, evidence_id, client_request_id, expected_revision):
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                row = await (await conn.execute(
                    "SELECT security.idp_subject_mapping_control(%s,%s,%s,%s,%s,%s) AS result",
                    (ctx.session_id, ctx.tenant_id, action, evidence_id,
                     client_request_id, expected_revision),
                )).fetchone()
            return row['result']
        except (psycopg.Error, ValueError) as error:
            self.translate(error)

    @staticmethod
    def translate(error):
        if isinstance(error, ValueError):
            raise AppError('TENANT_FORBIDDEN', 403) from None
        code = error.sqlstate
        message = getattr(getattr(error, 'diag', None), 'message_primary', '')
        if code == 'A0401':
            raise AppError('AUTH_REQUIRED', 401) from None
        if code == 'A0403':
            if message == 'VERIFIED_ASSURANCE_REQUIRED':
                raise AppError('IDP_ASSURANCE_REQUIRED', 403) from None
            raise AppError('REQUEST_FORBIDDEN', 403) from None
        if code == 'A0404':
            raise AppError('RESOURCE_NOT_FOUND', 404) from None
        if code == 'A0409':
            if message in ('IDEMPOTENCY_CONFLICT', 'MAPPING_ALREADY_ACTIVE'):
                raise AppError('IDP_MAPPING_CONFLICT', 409) from None
            raise AppError('REVISION_CONFLICT', 409) from None
        if code == 'A0422':
            raise AppError('REQUEST_INVALID', 422) from None
        if code == '42501':
            raise AppError('REQUEST_FORBIDDEN', 403) from None
        raise AppError('STORAGE_UNAVAILABLE', 503) from None
