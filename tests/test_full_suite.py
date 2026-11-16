"""Celoviti avtomatizirani testi za Moj knjižni kotiček (v1.0.5).

Preverja:
1. Povezavo z bazo, samodejne migracije in zdravje sistema (/health)
2. Registracijo uporabnikov, validacije (dolžina gesla, enoličnost, ujemanje)
3. Prijavo, zaščito pred brute-force napadi in zaklepanje računa (5 neuspelih poskusov)
4. Ponastavitev pozabljenega gesla prek varnega žetona (forgot/reset password)
5. Urejanje profila, spremembo gesla in preklic vseh sej (session revocation)
6. Vloge in pravice (ADMIN, EDITOR, USER, GUEST) ter strežniško ločevanje
7. Knjižnične operacije (dodajanje, urejanje, izposoja, vračilo, izvoz v Excel)
8. Varnostne kopije (ustvarjanje ZIP in obnova baze)
9. Varnostne glave in robots.txt
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Nastavitev izoliranega testnega okolja pred uvozom aplikacije
TEST_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TEST_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
os.chdir(str(PROJECT_DIR))

TEST_DB_FILE = TEST_DIR / "test_library.db"
if TEST_DB_FILE.is_file():
    try:
        TEST_DB_FILE.unlink()
    except OSError:
        pass

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_FILE.as_posix()}"
os.environ["APP_SECRET_KEY"] = "test-secret-key-super-secure-suite-32-chars-min"
os.environ["APP_ENV"] = "testing"
os.environ["SESSION_HTTPS_ONLY"] = "0"
os.environ["REGISTRATION_ENABLED"] = "1"

from starlette.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import application  # noqa: E402
from app.models import (  # noqa: E402
    Author,
    Book,
    Borrower,
    Genre,
    Loan,
    Location,
    PasswordReset,
    User,
    UserLocation,
)
from app.security import hash_password, verify_password  # noqa: E402
from app.server_backup import create_full_backup, restore_full_backup  # noqa: E402


class FullLibraryTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(application, follow_redirects=False)

        # Kreiranje privzetih testnih podatkov (lokacija + uporabniki za različne vloge)
        with SessionLocal() as db:
            loc = Location(name="Glavna testna knjižnica", address="Testna ulica 1", active=True)
            db.add(loc)
            db.flush()
            cls.location_id = loc.id

            admin_user = User(
                username="admin_test",
                display_name="Testni Administrator",
                email="admin@knjiznica-test.si",
                password_hash=hash_password("AdminPass123456!"),
                role="ADMIN",
                active=True,
                session_version=1,
            )
            editor_user = User(
                username="editor_test",
                display_name="Testni Urednik",
                email="editor@knjiznica-test.si",
                password_hash=hash_password("EditorPass123456!"),
                role="EDITOR",
                active=True,
                session_version=1,
            )
            regular_user = User(
                username="user_test",
                display_name="Testni Uporabnik",
                email="user@knjiznica-test.si",
                password_hash=hash_password("UserPass123456!"),
                role="USER",
                active=True,
                session_version=1,
            )
            guest_user = User(
                username="guest_test",
                display_name="Testni Gost",
                email="guest@knjiznica-test.si",
                password_hash=hash_password("GuestPass123456!"),
                role="GUEST",
                active=True,
                session_version=1,
            )
            db.add_all([admin_user, editor_user, regular_user, guest_user])
            db.flush()

            # Dodelitev lokacije
            for u in (admin_user, editor_user, regular_user, guest_user):
                db.add(UserLocation(user_id=u.id, location_id=loc.id))
            db.commit()

            cls.admin_id = admin_user.id
            cls.editor_id = editor_user.id
            cls.user_id = regular_user.id
            cls.guest_id = guest_user.id

    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        if TEST_DB_FILE.is_file():
            try:
                TEST_DB_FILE.unlink()
            except OSError:
                pass

    def _login(self, username: str, password: str) -> TestClient:
        c = TestClient(application, follow_redirects=False)
        res = c.post("/login", data={"username": username, "password": password, "next": "/"})
        self.assertEqual(res.status_code, 303, f"Prijava za {username} ni uspela: {res.text}")
        return c

    # 1. VARNOSTNE GLAVE, ROBOTS IN HEALTH
    def test_01_security_headers_and_robots(self):
        res = self.client.get("/robots.txt")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Disallow: /", res.text)
        self.assertEqual(res.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(res.headers.get("x-frame-options"), "SAMEORIGIN")

        res_health = self.client.get("/health")
        self.assertEqual(res_health.status_code, 200)
        self.assertEqual(res_health.json().get("status"), "ok")

    # 2. REGISTRACIJA IN VALIDACIJA
    def test_02_registration_validations(self):
        # Prekratko geslo (< 12)
        res = self.client.post("/register", data={
            "username": "kratko_geslo",
            "display_name": "Test",
            "email": "kratko@test.si",
            "password": "short",
            "confirm_password": "short",
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn("najmanj 12 znakov", res.text)

        # Neujemanje gesel
        res = self.client.post("/register", data={
            "username": "razlicno_geslo",
            "display_name": "Test",
            "email": "razlicno@test.si",
            "password": "Password1234567!",
            "confirm_password": "DifferentPassword123!",
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn("se ne ujemata", res.text)

        # Uspešna registracija
        res = self.client.post("/register", data={
            "username": "nov_uporabnik",
            "display_name": "Nov Registriran",
            "email": "novi@primer.si",
            "password": "ZeloVarnoGeslo2026!",
            "confirm_password": "ZeloVarnoGeslo2026!",
        })
        self.assertEqual(res.status_code, 303)
        self.assertIn("/login", res.headers.get("location", ""))

        # Zavrnitev podvojenega uporabniškega imena
        res_dup_user = self.client.post("/register", data={
            "username": "nov_uporabnik",
            "display_name": "Klon",
            "email": "drugi@primer.si",
            "password": "ZeloVarnoGeslo2026!",
            "confirm_password": "ZeloVarnoGeslo2026!",
        })
        self.assertEqual(res_dup_user.status_code, 200)
        self.assertIn("že zasedeno", res_dup_user.text)

        # Zavrnitev podvojenega e-poštnega naslova
        res_dup_email = self.client.post("/register", data={
            "username": "drugi_uporabnik",
            "display_name": "Drugi",
            "email": "novi@primer.si",
            "password": "ZeloVarnoGeslo2026!",
            "confirm_password": "ZeloVarnoGeslo2026!",
        })
        self.assertEqual(res_dup_email.status_code, 200)
        self.assertIn("že uporablja", res_dup_email.text)

    # 3. PRIJAVA, NEUSPELI POSKUSI IN ZAKLEPANJE RAČUNA
    def test_03_login_lockout_and_unlock(self):
        # 1-4 napačni poskusi
        for _ in range(4):
            res = self.client.post("/login", data={"username": "user_test", "password": "NapacnoGeslo!"})
            self.assertEqual(res.status_code, 200)
            self.assertIn("ni pravilno", res.text)

        # 5. napačni poskus sproži zaklep
        res_5 = self.client.post("/login", data={"username": "user_test", "password": "NapacnoGeslo!"})
        self.assertEqual(res_5.status_code, 200)
        self.assertIn("zaklenjen", res_5.text)

        # 6. poskus je takoj zavrnjen zaradi zaklepa
        res_6 = self.client.post("/login", data={"username": "user_test", "password": "UserPass123456!"})
        self.assertEqual(res_6.status_code, 200)
        self.assertIn("zaklenjen", res_6.text)

        # Odklep s strani administratorja
        admin_c = self._login("admin_test", "AdminPass123456!")
        res_unlock = admin_c.post(f"/admin/users/{self.user_id}/unlock")
        self.assertEqual(res_unlock.status_code, 303)

        # Po odklepu je prijava z veljavnim geslom spet možna
        res_ok = self.client.post("/login", data={"username": "user_test", "password": "UserPass123456!"})
        self.assertEqual(res_ok.status_code, 303)

    # 4. POZABLJENO GESLO IN PONASTAVITEV
    def test_04_forgot_and_reset_password(self):
        res_req = self.client.post("/forgot-password", data={"identifier": "user@knjiznica-test.si"})
        self.assertEqual(res_req.status_code, 200)
        self.assertIn("navodila za ponastavitev", res_req.text)

        # Pridobitev žetona iz baze
        with SessionLocal() as db:
            pr = db.scalar(
                select(PasswordReset)
                .where(PasswordReset.user_id == self.user_id, PasswordReset.used.is_(False))
                .order_by(PasswordReset.id.desc())
            )
            self.assertIsNotNone(pr)
            reset_token = pr.token

        # Obrazec za ponastavitev
        res_form = self.client.get(f"/reset-password?token={reset_token}")
        self.assertEqual(res_form.status_code, 200)

        # Ponastavitev gesla
        res_reset = self.client.post("/reset-password", data={
            "token": reset_token,
            "password": "NovoGesloUporabnika2026!",
            "confirm_password": "NovoGesloUporabnika2026!",
        })
        self.assertEqual(res_reset.status_code, 303)
        self.assertIn("/login", res_reset.headers.get("location", ""))

        # Prijava z novim geslom
        c = self._login("user_test", "NovoGesloUporabnika2026!")
        self.assertIsNotNone(c)

    # 5. UREJANJE PROFILA IN PREKLIC SEJ
    def test_05_profile_and_session_revocation(self):
        c = self._login("user_test", "NovoGesloUporabnika2026!")

        # Ogled profila
        res_view = c.get("/profile")
        self.assertEqual(res_view.status_code, 200)
        self.assertIn("Moj uporabniški profil", res_view.text)

        # Posodobitev podatkov
        res_update = c.post("/profile/update", data={
            "display_name": "Posodobljeni Uporabnik",
            "email": "posodobljen@knjiznica-test.si",
        })
        self.assertEqual(res_update.status_code, 303)

        # Sprememba gesla znotraj profila
        res_chpass = c.post("/profile/password", data={
            "current_password": "NovoGesloUporabnika2026!",
            "new_password": "SeNovejseGeslo2026!",
            "confirm_password": "SeNovejseGeslo2026!",
        })
        self.assertEqual(res_chpass.status_code, 303)

        # Preklic vseh obstoječih sej
        res_revoke = c.post("/profile/logout-all")
        self.assertEqual(res_revoke.status_code, 303)

        # Neavtenticiran odziv za neznano sejo
        old_session_client = TestClient(application, follow_redirects=False)
        res_unauth = old_session_client.get("/")
        self.assertEqual(res_unauth.status_code, 303)
        self.assertIn("/login", res_unauth.headers.get("location", ""))

    # 6. VLOGE IN DOSTOPI (ADMIN, EDITOR, USER, GUEST)
    def test_06_rbac_permissions(self):
        admin_c = self._login("admin_test", "AdminPass123456!")
        editor_c = self._login("editor_test", "EditorPass123456!")
        user_c = self._login("user_test", "SeNovejseGeslo2026!")
        guest_c = self._login("guest_test", "GuestPass123456!")

        # Admin ima dostop do /admin
        self.assertEqual(admin_c.get("/admin").status_code, 200)

        # Urednik, Uporabnik in Gost nimajo dostopa do /admin (403 prepovedano)
        for client, name in ((editor_c, "editor"), (user_c, "user"), (guest_c, "guest")):
            res = client.get("/admin")
            self.assertIn(res.status_code, (403, 303), f"{name} ne sme dostopati do /admin")

        # Gost NE sme dodajati knjig (prejme 403)
        res_guest_add = guest_c.post("/books/save", data={"title": "Gostova knjiga"})
        self.assertEqual(res_guest_add.status_code, 403)

        # Urednik LAHKO dodaja knjige
        res_editor_add = editor_c.post("/books/save", data={
            "title": "Knjiga Urednika",
            "authors": "Ivan Cankar",
            "publisher": "Mladinska knjiga",
            "genre": "Leposlovje",
            "inventory_no": "TEST-ED-001",
        })
        self.assertEqual(res_editor_add.status_code, 303)
        self.assertIn("/books/", res_editor_add.headers.get("location", ""))

    # 7. KNJIŽNIČNE OPERACIJE, IZPOSOJE IN IZVOZI
    def test_07_books_loans_and_exports(self):
        admin_c = self._login("admin_test", "AdminPass123456!")

        # Dodajanje nove knjige
        res_add = admin_c.post("/books/save", data={
            "title": "Bralna poslastica",
            "authors": "France Prešeren",
            "publisher": "Cankarjeva založba",
            "genre": "Poezija",
            "inventory_no": "POEZ-001",
            "year": "1847",
        })
        self.assertEqual(res_add.status_code, 303)
        book_url = res_add.headers.get("location", "")
        book_id = int(book_url.split("/")[-1])

        # Preverjanje prisotnosti v katalogu
        res_cat = admin_c.get("/books")
        self.assertEqual(res_cat.status_code, 200)
        self.assertIn("Bralna poslastica", res_cat.text)

        # Dodajanje izposojevalca (Borrower)
        with SessionLocal() as db:
            borrower = Borrower(first_name="Marko", last_name="Bralec", location_id=self.location_id)
            db.add(borrower)
            db.commit()
            borrower_id = borrower.id

        # Izposoja knjige
        res_loan = admin_c.post(f"/books/{book_id}/loan", data={
            "borrower_id": borrower_id,
            "due_date": "2026-12-31",
        })
        self.assertEqual(res_loan.status_code, 303)

        # Preverjanje statusa izposojene knjige
        res_book_view = admin_c.get(f"/books/{book_id}")
        self.assertEqual(res_book_view.status_code, 200)
        self.assertIn("POSOJENA", res_book_view.text)

        # Vračilo knjige
        with SessionLocal() as db:
            b = db.get(Book, book_id)
            active_loan = [l for l in b.loans if l.returned_date is None][0]
            loan_id = active_loan.id

        res_return = admin_c.post(f"/loans/{loan_id}/return", data={"next": f"/books/{book_id}"})
        self.assertEqual(res_return.status_code, 303)

        # Knjiga je spet na voljo
        res_book_view2 = admin_c.get(f"/books/{book_id}")
        self.assertIn("NA VOLJO", res_book_view2.text)

        # Izvoz v Excel
        res_excel = admin_c.get("/books/export.xlsx")
        self.assertEqual(res_excel.status_code, 200)
        self.assertIn("spreadsheetml", res_excel.headers.get("content-type", ""))
        self.assertGreater(len(res_excel.content), 500)

    # 8. VARNOSTNE KOPIJE IN OBNOVA
    def test_08_full_backup_and_restore(self):
        admin_c = self._login("admin_test", "AdminPass123456!")

        # Ustvarjanje varnostne kopije
        backup_bytes = create_full_backup()
        self.assertGreater(len(backup_bytes), 100)

        # Obnova baze iz ustvarjene kopije
        restore_full_backup(backup_bytes, "moj-knjizni-koticek-backup.zip")

        # Preverjanje, da so podatki po obnovi še vedno veljavni in dostopni
        with SessionLocal() as db:
            user_count = db.scalar(select(User).where(User.username == "admin_test"))
            self.assertIsNotNone(user_count)

    # 9. SMTP NASTAVITVE IN POŠILJANJE PRIJAVNIH PODATKOV
    def test_09_smtp_settings_and_credentials_email(self):
        admin_c = self._login("admin_test", "AdminPass123456!")

        # Shrani SMTP nastavitve prek admin vmesnika
        res_save = admin_c.post("/admin/smtp/save", data={
            "smtp_host": "mail.knjiznica-test.si",
            "smtp_port": "587",
            "smtp_user": "obvestila@knjiznica-test.si",
            "smtp_password": "SmtpSuperSecretPassword123!",
            "smtp_from": "knjiznica@knjiznica-test.si",
            "smtp_from_name": "Moj knjižni kotiček Test",
            "smtp_security": "tls",
        })
        self.assertEqual(res_save.status_code, 303)

        # Preveri, ali so nastavitve shranjene v bazi
        with SessionLocal() as db:
            from app.models import AppSetting
            from app.mailer import get_smtp_config, is_smtp_configured
            cfg = get_smtp_config(db)
            self.assertEqual(cfg["host"], "mail.knjiznica-test.si")
            self.assertEqual(cfg["port"], 587)
            self.assertEqual(cfg["user"], "obvestila@knjiznica-test.si")
            self.assertEqual(cfg["from_email"], "knjiznica@knjiznica-test.si")
            self.assertEqual(cfg["security"], "tls")
            self.assertTrue(is_smtp_configured(db))

        # Preveri, da admin stran prikazuje novo konfiguracijo
        res_admin = admin_c.get("/admin")
        self.assertEqual(res_admin.status_code, 200)
        self.assertIn("mail.knjiznica-test.si", res_admin.text)
        self.assertIn("SMTP strežnik je aktiven", res_admin.text)

        # Ustvari novega uporabnika s kljukico za pošiljanje prijavnih podatkov
        res_new_user = admin_c.post("/admin/users/save", data={
            "username": "novi_bralec",
            "display_name": "Novi Bralec",
            "email": "novi.bralec@knjiznica-test.si",
            "password": "ZeloVarnoGeslo2026!",
            "role": "USER",
            "send_credentials": "1",
        })
        self.assertEqual(res_new_user.status_code, 303)

        with SessionLocal() as db:
            created_user = db.scalar(select(User).where(User.username == "novi_bralec"))
            self.assertIsNotNone(created_user)
            user_id = created_user.id

        # Ponastavi geslo uporabniku s kljukico za pošiljanje na e-pošto
        res_reset_pass = admin_c.post(f"/admin/users/{user_id}/password", data={
            "password": "PopolnomaNovoGeslo2026!",
            "send_credentials": "1",
        })
        self.assertEqual(res_reset_pass.status_code, 303)

        # Preizkus prijave z novim geslom
        new_c = self._login("novi_bralec", "PopolnomaNovoGeslo2026!")
        res_profile = new_c.get("/profile")
        self.assertEqual(res_profile.status_code, 200)
        self.assertIn("Novi Bralec", res_profile.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
