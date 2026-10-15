"""Model contracts: maps model references to runtime token limits and pricing estimates."""
from app.ai.pricing import PRICE
from app.ai.model_registry import APPROVED_MODELS, GLOBAL_REGISTRY

MODEL_CONTRACTS = {
    'default_general': {'execution_kind': 'general', 'generation_model': PRICE.generation_model, 'embedding_model': None},
    'default_rules_rag': {'execution_kind': 'rules_rag', 'generation_model': PRICE.generation_model, 'embedding_model': PRICE.embedding_model},
}

def contract(model_ref: str, execution_kind: str = 'general'):
    if model_ref in MODEL_CONTRACTS:
        return {
            **MODEL_CONTRACTS[model_ref],
            'model_ref': model_ref,
            'max_input_tokens': 6000,
            'max_completion_tokens': 1024,
            'max_embedding_tokens': 4000,
            'price_version': PRICE.version,
            'price_basis': 'frozen_internal_estimate'
        }
    model = GLOBAL_REGISTRY.resolve(model_ref)
    return {
        'model_ref': model.model_id,
        'execution_kind': execution_kind,
        'generation_model': model.model_name,
        'embedding_model': PRICE.embedding_model if execution_kind == 'rules_rag' else None,
        'max_input_tokens': min(model.context_window, 128000),
        'max_completion_tokens': min(model.max_output_tokens, 4096),
        'max_embedding_tokens': 4000,
        'price_version': model.pricing_version,
        'price_basis': 'frozen_internal_estimate'
    }
