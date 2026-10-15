from app.main import create_app as base
from app.config import Settings
def create_app():
 return base(Settings(mode='mock',execution_enabled=False,index_enabled=False,openai_api_key=None))
