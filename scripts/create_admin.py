"""Create the first administrator on non-interactive cPanel hosting."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# app.config loads the private .env file before these values are read.
from sqlalchemy import func, select
from app.database import Base, engine, SessionLocal
from app.models import FamilyMember, Location, User
from app.security import hash_password

BOOTSTRAP_KEYS = {
    "BOOTSTRAP_LOCATION_NAME",
    "BOOTSTRAP_ADMIN_USERNAME",
    "BOOTSTRAP_ADMIN_DISPLAY_NAME",
    "BOOTSTRAP_ADMIN_PASSWORD",
}


def clear_bootstrap_values() -> bool:
    """Remove one-time credentials from .env after successful creation."""
    env_path = ROOT / ".env"
    try:
        if env_path.is_file():
            mode = env_path.stat().st_mode & 0o777
            original_lines = env_path.read_text(encoding="utf-8").splitlines()
            kept_lines = []
            for line in original_lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    kept_lines.append(line)
                    continue
                key = stripped.split("=", 1)[0].strip()
                if key not in BOOTSTRAP_KEYS:
                    kept_lines.append(line)

            fd, temp_name = tempfile.mkstemp(prefix=".env-", suffix=".tmp", dir=str(ROOT))
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write("\n".join(kept_lines).rstrip() + "\n")
                os.chmod(temp_name, mode)
                Path(temp_name).replace(env_path)
            except Exception:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
                raise
    except OSError:
        return False

    for key in BOOTSTRAP_KEYS:
        os.environ.pop(key, None)
    return True


def main() -> int:
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip().lower()
    display_name = os.getenv("BOOTSTRAP_ADMIN_DISPLAY_NAME", "Administrator").strip()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    location_name = os.getenv("BOOTSTRAP_LOCATION_NAME", "Prva lokacija").strip()

    missing = []
    if not username:
        missing.append("BOOTSTRAP_ADMIN_USERNAME")
    if not password:
        missing.append("BOOTSTRAP_ADMIN_PASSWORD")
    if missing:
        print("NAPAKA: V .env manjkajo: " + ", ".join(missing))
        print("Dodaj začasne BOOTSTRAP_* nastavitve in ponovno zaženi skripto.")
        return 2

    if len(username) > 80 or any(char.isspace() for char in username):
        print("NAPAKA: Uporabniško ime mora imeti največ 80 znakov in ne sme vsebovati presledkov.")
        return 2
    if len(password) < 12:
        print("NAPAKA: Geslo mora vsebovati najmanj 12 znakov.")
        return 2

    display_name = display_name or "Administrator"
    location_name = location_name or "Prva lokacija"

    try:
        # Create only missing tables. Existing records are not modified.
        Base.metadata.create_all(bind=engine)

        with SessionLocal() as db:
            existing = db.scalar(
                select(User).where(func.lower(User.username) == username).limit(1)
            )
            if existing is not None:
                if existing.role == "ADMIN" and existing.active:
                    print("Administrator s tem uporabniškim imenom že obstaja.")
                    print("Novega računa nisem ustvaril.")
                    if clear_bootstrap_values():
                        print("Začasne BOOTSTRAP_* nastavitve so odstranjene iz .env.")
                    else:
                        print("OPOZORILO: Ročno odstrani začasne BOOTSTRAP_* vrstice iz .env.")
                    return 0
                print("NAPAKA: Uporabniško ime že uporablja drug račun. Izberi drugo ime.")
                return 3

            location = db.scalar(
                select(Location)
                .where(func.lower(Location.name) == location_name.lower())
                .limit(1)
            )
            if location is None:
                location = Location(name=location_name, active=True)
                db.add(location)
                db.flush()
            elif not location.active:
                location.active = True

            user = User(
                username=username,
                display_name=display_name,
                password_hash=hash_password(password),
                role="ADMIN",
                active=True,
            )
            db.add(user)
            db.flush()

            db.add(FamilyMember(
                name=display_name,
                location_id=location.id,
                user_id=user.id,
                active=True,
            ))
            db.commit()
            location_id = location.id
            saved_location_name = location.name

        print("USPEH: Podatkovne tabele so pripravljene.")
        print("USPEH: Prvi administratorski račun je ustvarjen.")
        print(f"Uporabniško ime: {username}")
        print(f"Začetna lokacija: {saved_location_name} (ID {location_id})")
        if clear_bootstrap_values():
            print("USPEH: Začasne BOOTSTRAP_* nastavitve so odstranjene iz .env.")
        else:
            print("OPOZORILO: Administrator je ustvarjen, vendar odstrani BOOTSTRAP_* vrstice iz .env ročno.")
        print("Zdaj se lahko prijaviš na /login.")
        return 0

    except Exception as exc:
        print("NAPAKA PRI USTVARJANJU ADMINISTRATORJA:")
        print(f"{type(exc).__name__}: {exc}")
        print("Preveri DB povezavo in dnevnike. Gesel ne kopiraj v klepet.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
