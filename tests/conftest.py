import pytest

import config
import db


@pytest.fixture
def basis_data(tmp_path, monkeypatch):
    """Database dan folder output sementara untuk tiap tes."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "uji.db")
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    db._SIAP.clear()
    return tmp_path / "uji.db"
