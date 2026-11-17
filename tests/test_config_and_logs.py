import logging
import subprocess
from pathlib import Path

from prognozy import cli
from prognozy.config import Settings, missing_requirements
from prognozy.logs import SecretRedactingFilter

REPO = Path(__file__).resolve().parents[1]


def test_publish_is_off_by_default():
    assert Settings.from_env().publish is False


def test_missing_keys_reported(monkeypatch):
    assert len(missing_requirements()) == 2
    monkeypatch.setenv("METACULUS_TOKEN", "REPLACE_ME")
    assert len(missing_requirements()) == 2  # zaślepka to nie klucz
    monkeypatch.setenv("METACULUS_TOKEN", "tok-abcdef123")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-abcdef123")
    assert missing_requirements() == []


def test_run_refuses_without_keys():
    assert cli.main(["run", "--mode", "test", "--dry-run"]) == 1


def test_secrets_are_masked_in_logs(monkeypatch, caplog):
    secret = "sk-or-SUPERSECRET-987654"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    logger = logging.getLogger("test.redact")
    caplog.handler.addFilter(SecretRedactingFilter())
    with caplog.at_level(logging.INFO):
        logger.info("klucz to %s", secret)
        try:
            raise ValueError(f"auth failed for {secret}")
        except ValueError:
            logger.exception("błąd")
    assert secret not in caplog.text
    assert "***" in caplog.text


def test_no_secrets_or_env_files_tracked_in_repo():
    files = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    assert ".env" not in files
    assert not any(f.endswith(".env") and not f.endswith(".example") for f in files)
