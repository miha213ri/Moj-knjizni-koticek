from pathlib import Path
import os

from sqlalchemy.engine import URL, make_url

BASE_DIR = Path(__file__).resolve().parent.parent


def _read_env_file(path: Path) -> dict[str, str]:
    """Read UTF-8 KEY=VALUE settings without writing values to os.environ.

    On some shared-hosting Passenger setups, os.environ uses an ASCII
    encoding. A non-ASCII .env value such as a Slovenian location name must
    therefore remain in this Python dictionary.
    """
    values: dict[str, str] = {}
    if not path.is_file():
        return values

    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
            value = value[1:-1]
        if key:
            values[key] = value
    return values


_ENV_FILE = _read_env_file(BASE_DIR / ".env")


def get_setting(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is not None:
        return value
    return _ENV_FILE.get(name, default)


APP_ENV = get_setting("APP_ENV", "development").lower()
APP_TITLE = "Moj knjižni kotiček"
APP_SECRET_KEY = get_setting("APP_SECRET_KEY")
SESSION_HTTPS_ONLY = get_setting("SESSION_HTTPS_ONLY", "1").lower() not in ("0", "false", "no")

DATABASE_URL = get_setting("DATABASE_URL").strip()
if not DATABASE_URL and get_setting("DB_NAME") and get_setting("DB_USER"):
    DATABASE_URL = URL.create(
        "mysql+pymysql",
        username=get_setting("DB_USER"),
        password=get_setting("DB_PASSWORD"),
        host=get_setting("DB_HOST", "localhost"),
        port=int(get_setting("DB_PORT", "3306")),
        database=get_setting("DB_NAME"),
        query={"charset": "utf8mb4"},
    ).render_as_string(hide_password=False)

if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{(BASE_DIR / 'local_library.db').as_posix()}"

# A complete DATABASE_URL from cPanel may omit charset or specify an older
# charset. Override it so every PyMySQL connection uses utf8mb4.
if DATABASE_URL.startswith("mysql+pymysql://"):
    parsed_url = make_url(DATABASE_URL)
    query = dict(parsed_url.query)
    query["charset"] = "utf8mb4"
    DATABASE_URL = parsed_url.set(query=query).render_as_string(hide_password=False)

if APP_ENV == "production":
    if len(APP_SECRET_KEY) < 40:
        raise RuntimeError(
            "APP_SECRET_KEY mora vsebovati najmanj 40 znakov. "
            "Ustvari naključen ključ in ga vnesi v .env."
        )
    if not DATABASE_URL.startswith("mysql+pymysql://"):
        raise RuntimeError(
            "Produkcija mora uporabljati MariaDB. Preveri DB_HOST, DB_NAME, "
            "DB_USER in DB_PASSWORD v .env."
        )

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
