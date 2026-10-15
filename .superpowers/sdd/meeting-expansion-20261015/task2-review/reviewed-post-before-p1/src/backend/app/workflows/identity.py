"""An approval seals the deployed workflow interpreter and its SQL contract."""
import hashlib
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def runtime_digest():
    directory=Path(__file__).parent
    paths=[directory/'approved_models.py',directory/'bindings.py',directory/'service.py',directory/'repository.py',directory/'identity.py',directory.parents[1]/'migrations/048_workflow_execution_ledger.sql']
    paths.extend([directory.parent/'use_cases/meeting.py',directory.parent/'use_cases/catalog.py',directory.parent/'use_cases/service.py',directory.parents[1]/'migrations/049_meeting_workflow_binding.sql'])
    paths.append(directory.parents[1]/'migrations/050_tool_workflow_approval_reviews.sql')
    paths.extend([directory.parent/'use_cases/meeting_dates.py',directory.parent/'use_cases/meeting_quality.py',directory.parent/'use_cases/runtime.py',directory.parents[1]/'migrations/051_meeting_context_quality.sql'])
    paths.extend([directory.parent/'use_cases/routes.py',directory.parent/'ai/repository.py',directory.parent/'assets/published.py'])
    digest=hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode());digest.update(b'\0');digest.update(path.read_bytes());digest.update(b'\0')
    return digest.hexdigest()
