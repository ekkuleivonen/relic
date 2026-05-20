from pathlib import Path

import seed as seed_module


def test_run_migrations_upgrades_to_head(monkeypatch):
    calls = {}

    class FakeConfig:
        def __init__(self, config_file):
            calls["config_file"] = config_file
            self.options = {}

        def set_main_option(self, key, value):
            self.options[key] = value

    def fake_upgrade(config, revision):
        calls["config"] = config
        calls["revision"] = revision

    monkeypatch.setattr(seed_module, "Config", FakeConfig)
    monkeypatch.setattr(seed_module.command, "upgrade", fake_upgrade)

    seed_module.run_migrations()

    server_dir = Path(seed_module.__file__).resolve().parent
    assert calls["config_file"] == str(server_dir / "alembic.ini")
    assert calls["config"].options["script_location"] == str(server_dir / "alembic")
    assert calls["revision"] == "head"


def test_main_runs_migrations_before_seed(monkeypatch):
    calls = []

    monkeypatch.setattr(seed_module, "run_migrations", lambda: calls.append("migrations"))
    monkeypatch.setattr(seed_module, "seed", lambda: calls.append("seed"))

    seed_module.main()

    assert calls == ["migrations", "seed"]


def test_upsert_seed_folder_creates_starter_folder(db_session, monkeypatch):
    monkeypatch.setattr(seed_module.S, "RELIC_SEED_FOLDER_NAME", "Uploads")

    root = seed_module.upsert_root_folder(db_session)
    db_session.commit()

    folder = seed_module.upsert_seed_folder(db_session, root)
    db_session.commit()

    assert folder is not None
    assert folder.name == "Uploads"
    assert folder.parent_id == root.id

    again = seed_module.upsert_seed_folder(db_session, root)
    assert again.id == folder.id


def test_upsert_seed_folder_skipped_when_name_blank(db_session, monkeypatch):
    monkeypatch.setattr(seed_module.S, "RELIC_SEED_FOLDER_NAME", "  ")

    root = seed_module.upsert_root_folder(db_session)
    db_session.commit()

    assert seed_module.upsert_seed_folder(db_session, root) is None
