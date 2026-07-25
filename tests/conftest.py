"""Shared pytest fixtures."""

from __future__ import annotations

import os
import tempfile

import pytest

from gsid import db
from gsid.config import Config
from gsid.seed import seed_all


@pytest.fixture()
def config(tmp_path):
    return Config(
        db_path=str(tmp_path / "test.sqlite3"),
        data_mode="demo",
        ai_provider="heuristic",
    )


@pytest.fixture()
def conn(config):
    c = db.connect(config.db_file)
    db.init_db(c)
    seed_all(c, config, force=True)
    yield c
    c.close()


@pytest.fixture()
def client(config):
    from gsid.app import create_app

    app = create_app(config)
    app.testing = True
    with app.test_client() as cl:
        yield cl
