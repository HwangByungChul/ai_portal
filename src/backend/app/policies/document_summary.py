"""Summary input and combined output minimum policy; never rewrite offsets."""
from app.policies.document_ingest import require_document_policy
REVISION='summary-v1'
def require_summary_policy(title,text):
    require_document_policy(title+'\n'+text)
