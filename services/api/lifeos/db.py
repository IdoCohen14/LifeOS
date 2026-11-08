import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase

ROOT = Path(__file__).resolve().parents[3]


class Base(DeclarativeBase):
    pass


def data_directory() -> Path:
    # Keep private data outside repositories that may be synced by OneDrive.
    if os.name == "nt":
        default = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "LifeOS"
    else:
        default = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "lifeos"
    path = Path(os.environ.get("LIFEOS_DATA_DIR") or default).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def open_database(directory: Path):
    engine = create_engine(
        "sqlite:///" + str(directory / "lifeos.sqlite3"), connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")

    return engine


def migrate(engine):
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
