import io
import os
import pathlib

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import get_settings

BACKEND = pathlib.Path(__file__).resolve().parents[1]
URL_ENV = os.environ.get("TEST_DATABASE_URL")


def config() -> Config:
    return Config(str(BACKEND / "alembic.ini"))


@pytest.fixture
def database_url(monkeypatch):
    def apply(url):
        monkeypatch.setenv("DATABASE_URL", url)
        get_settings.cache_clear()

    yield apply
    get_settings.cache_clear()


def test_there_is_exactly_one_baseline_revision():
    script = ScriptDirectory.from_config(config())
    assert script.get_heads() == ["0001_baseline"]
    assert script.get_revision("0001_baseline").down_revision is None


def test_the_ini_file_holds_no_connection_string():
    text = (BACKEND / "alembic.ini").read_text()
    assert "sqlalchemy.url" not in text.replace("# ", "").split("[loggers]")[0].replace("DATABASE_URL", "")
    assert "postgres://" not in text and "postgresql://" not in text


def test_offline_sql_keeps_alembic_bookkeeping_out_of_the_public_schema(database_url):
    database_url("postgresql://user:YOUR_PASSWORD@db.example.com:5432/postgres")
    cfg = config()
    cfg.output_buffer = io.StringIO()
    command.upgrade(cfg, "head", sql=True)
    sql = cfg.output_buffer.getvalue()
    assert "CREATE TABLE alembic.alembic_version" in sql
    assert "public.alembic_version" not in sql
    assert "0001_baseline" in sql


def test_missing_database_url_stops_with_a_clear_message(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(BACKEND)
    get_settings.cache_clear()
    try:
        monkeypatch.setattr("app.core.config.Settings.model_config", {**__import__("app.core.config", fromlist=["Settings"]).Settings.model_config, "env_file": None})
        cfg = config()
        cfg.output_buffer = io.StringIO()
        with pytest.raises(SystemExit) as info:
            command.upgrade(cfg, "head", sql=True)
        assert "DATABASE_URL" in str(info.value)
    finally:
        get_settings.cache_clear()


@pytest.mark.skipif(not URL_ENV, reason="set TEST_DATABASE_URL to a throwaway database named *test*")
def test_stamp_records_the_baseline_in_a_private_schema(database_url):
    import psycopg

    database_url(URL_ENV)
    with psycopg.connect(URL_ENV, autocommit=True) as admin:
        assert "test" in admin.execute("SELECT current_database()").fetchone()[0]
        admin.execute("DROP SCHEMA IF EXISTS alembic CASCADE")
    try:
        command.stamp(config(), "head")
        command.upgrade(config(), "head")  # already at head: must be a no-op
        with psycopg.connect(URL_ENV) as conn:
            assert conn.execute("SELECT version_num FROM alembic.alembic_version").fetchall() == [("0001_baseline",)]
            assert conn.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'alembic_version'"
            ).fetchone() == (0,)
    finally:
        with psycopg.connect(URL_ENV, autocommit=True) as admin:
            admin.execute("DROP SCHEMA IF EXISTS alembic CASCADE")
