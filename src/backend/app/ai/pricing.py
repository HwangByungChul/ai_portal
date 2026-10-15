"""Frozen conservative internal KRW estimate; never a provider invoice."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from app.ai.types import Operation, UsageReceipt

@dataclass(frozen=True)
class PriceSnapshot:
    version: str = 'price-20261004-v1'
    generation_model: str = 'gpt-4o-mini'
    embedding_model: str = 'text-embedding-3-small'
    input_usd_per_million: Decimal = Decimal('0.15')
    output_usd_per_million: Decimal = Decimal('0.60')
    embedding_usd_per_million: Decimal = Decimal('0.02')
    krw_per_usd: Decimal = Decimal('2000')
    protection_factor: Decimal = Decimal('1.2')
    quantum_krw: Decimal = Decimal('0.01')

    def as_dict(self) -> dict:
        return {key: str(value) for key, value in vars(self).items()}

PRICE = PriceSnapshot()


def _krw(input_tokens: int, output_tokens: int, *, embedding: bool = False) -> Decimal:
    input_price = PRICE.embedding_usd_per_million if embedding else PRICE.input_usd_per_million
    usd = (Decimal(input_tokens) * input_price + Decimal(output_tokens) * PRICE.output_usd_per_million) / Decimal(1000000)
    return (usd * PRICE.krw_per_usd * PRICE.protection_factor).quantize(PRICE.quantum_krw, rounding=ROUND_CEILING)


def reservation_krw(operation: Operation) -> Decimal:
    if operation in ('generate_general', 'generate_rag'):
        return _krw(6000, 1024)
    if operation == 'embed_query':
        return _krw(4000, 0, embedding=True)
    if operation == 'embed_document':
        return _krw(4096, 0, embedding=True)
    raise ValueError('OPERATION_REJECTED')


def cost_krw(receipt: UsageReceipt) -> Decimal:
    tokens = (receipt.input_tokens, receipt.output_tokens, receipt.total_tokens)
    if (any(type(n) is not int or not 0 <= n <= 9223372036854775807 for n in tokens)
            or receipt.total_tokens != receipt.input_tokens + receipt.output_tokens
            or receipt.observed_tier != 'default'):
        raise ValueError('USAGE_RECEIPT_REJECTED')
    if receipt.provider_request_id is not None and (not isinstance(receipt.provider_request_id, str)
            or not 1 <= len(receipt.provider_request_id) <= 256 or not receipt.provider_request_id.isascii()
            or any(ord(c) < 33 or ord(c) > 126 for c in receipt.provider_request_id)):
        raise ValueError('USAGE_RECEIPT_REJECTED')
    if receipt.observed_model in ('gpt-4o-mini', 'gpt-4o-mini-2024-07-18'):
        return _krw(receipt.input_tokens, receipt.output_tokens)
    if receipt.observed_model == 'text-embedding-3-small' and receipt.output_tokens == 0:
        return _krw(receipt.input_tokens, 0, embedding=True)
    from app.ai.model_registry import APPROVED_MODELS
    ref = APPROVED_MODELS.get(receipt.observed_model)
    if ref is not None:
        usd = (Decimal(receipt.input_tokens) * ref.input_usd_per_million + Decimal(receipt.output_tokens) * ref.output_usd_per_million) / Decimal(1000000)
        return (usd * PRICE.krw_per_usd * PRICE.protection_factor).quantize(PRICE.quantum_krw, rounding=ROUND_CEILING)
    raise ValueError('USAGE_RECEIPT_REJECTED')
