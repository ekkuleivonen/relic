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
