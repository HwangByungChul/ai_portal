import asyncio
import pytest
from app.db import make_web_pool
from scripts.devdb import DevCluster
from scripts.migrate import create_fixture_database,apply_migrations
from scripts.seed import seed_fixture
from support import FixtureState
from psycopg.conninfo import make_conninfo

@pytest.fixture(scope='session')
def owned_cluster():
    cluster=DevCluster(); prior=cluster.status()['state']
    if prior!='running': cluster.start()
    try: yield cluster
    finally:
        if prior!='running': cluster.stop()

@pytest.fixture
def db_fixture(owned_cluster):
    db=create_fixture_database(); loop=asyncio.new_event_loop(); pool=None; state=None
    try:
        apply_migrations(db); state=seed_fixture(db)
        pool=make_web_pool(db.runtime_dsn(),size=1)
        loop.run_until_complete(pool.open()); loop.run_until_complete(pool.wait(timeout=5))
        yield FixtureState(db,state,loop,pool,make_conninfo(host='127.0.0.1',port=55432,dbname=db.name,user='mvp_bootstrap',passfile=str(db.cluster.passfile_path)),
                           state.passwords)
    finally:
        if pool: loop.run_until_complete(pool.close())
        loop.close()
        db.drop()
        if state: state.secret_path.unlink(missing_ok=True)

@pytest.fixture
def fixture_state(db_fixture): return db_fixture

@pytest.fixture
def auth_settings(db_fixture):
    from pydantic import SecretStr
    from app.config import Settings
    from app.auth.crypto import new_secret
    return Settings(web_dsn=SecretStr(db_fixture.db.runtime_dsn()),login_hmac_secret=SecretStr(new_secret()))

@pytest.fixture
def client(auth_settings):
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app(auth_settings),base_url='http://127.0.0.1:8000',client=('127.0.0.1',50000)) as client:
        yield client

@pytest.fixture
def login(db_fixture):
    from support import login as perform_login
    def call(client,actor):
        return perform_login(client,actor,db_fixture.passwords)
    return call
