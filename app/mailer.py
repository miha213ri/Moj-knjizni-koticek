"""Sistemsko pošiljanje e-poštnih sporočil (SMTP) s podporo za bazo in varno beleženje."""
from __future__ import annotations

import logging
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Any

from app.config import (
    APP_TITLE,
    BASE_DIR,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_TLS,
    SMTP_USER,
)

logger = logging.getLogger(__name__)


def get_smtp_config(db=None) -> dict[str, Any]:
    """Pridobi SMTP nastavitve iz baze podatkov (AppSetting) s privzetim preklopom na .env."""
    db_config: dict[str, str] = {}
    if db is not None:
        try:
            from app.models import AppSetting
            settings_rows = db.query(AppSetting).filter(AppSetting.key.like("smtp_%")).all()
            for row in settings_rows:
                db_config[row.key] = row.value or ""
        except Exception as exc:
            logger.debug("Branje SMTP iz baze ni uspelo: %s", exc)

    host = (db_config.get("smtp_host") or SMTP_HOST or "").strip()
    port_val = db_config.get("smtp_port") or str(SMTP_PORT or 587)
    try:
        port = int(port_val)
    except Exception:
        port = 587

    user = (db_config.get("smtp_user") or SMTP_USER or "").strip()
    password = db_config.get("smtp_password") if "smtp_password" in db_config else (SMTP_PASSWORD or "")
    from_email = (db_config.get("smtp_from") or SMTP_FROM or "knjiznica@primer.si").strip()
    from_name = (db_config.get("smtp_from_name") or APP_TITLE).strip()
    security = (db_config.get("smtp_security") or ("tls" if SMTP_TLS else "none")).strip().lower()

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "from_email": from_email,
        "from_name": from_name,
        "security": security,
    }


def is_smtp_configured(db=None) -> bool:
    """Preveri, ali so vneseni osnovni podatki za delovanje SMTP strežnika."""
    cfg = get_smtp_config(db)
    return bool(cfg["host"])


def test_smtp_connection(
    host: str,
    port: int,
    user: str,
    password: str,
    security: str,
    from_email: str,
    from_name: str,
    test_recipient: str,
) -> tuple[bool, str]:
    """Preizkusi povezavo s poštnim strežnikom SMTP in pošlje potrditveno e-pošto."""
    host = host.strip()
    test_recipient = test_recipient.strip()
    if not host:
        return False, "SMTP gostitelj (Host) ne sme biti prazen."
    if not test_recipient or "@" not in test_recipient:
        return False, "Vnesite veljaven e-poštni naslov prejemnika testnega sporočila."

    from_addr = from_email.strip() or user or "knjiznica@primer.si"
    sender_name = from_name.strip() or APP_TITLE

    try:
        if security == "ssl" or port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=12)
        else:
            server = smtplib.SMTP(host, port, timeout=12)
            server.ehlo()
            if security == "tls" or port in (587, 25):
                server.starttls()
                server.ehlo()

        if user and password:
            server.login(user, password)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Testna povezava · {APP_TITLE}"
        msg["From"] = formataddr((str(Header(sender_name, "utf-8")), from_addr))
        msg["To"] = test_recipient

        text_body = (
            f"Pozdravljeni!\n\n"
            f"To je samodejno preizkusno sporočilo sistema {APP_TITLE}.\n"
            f"Povezava s poštnim strežnikom SMTP ({host}:{port}) deluje brezhibno.\n\n"
            f"Sistem lahko sedaj zanesljivo pošilja prijavne podatke, gesla in povezave za ponastavitev."
        )
        html_body = f"""<!doctype html>
<html lang="sl">
<head><meta charset="utf-8"></head>
<body style="font-family:system-ui,-apple-system,sans-serif; background:#f8fafc; color:#1e293b; padding:24px;">
  <div style="max-width:540px; margin:auto; background:#ffffff; border-radius:8px; border:1px solid #10b981; padding:24px;">
    <h2 style="color:#1e3a8a; margin-top:0;">📚 {APP_TITLE}</h2>
    <p>Pozdravljeni!</p>
    <p style="color:#065f46; background:#ecfdf5; padding:12px; border-radius:6px; font-weight:bold;">
      ✓ Testna povezava s poštnim strežnikom SMTP je bila USPEŠNO vzpostavljena!
    </p>
    <p>Povezava s strežnikom <strong>{host}:{port}</strong> deluje pravilno. Sistem je pripravljen za pošiljanje obvestil in ponastavitev gesel na e-pošto uporabnikov.</p>
    <hr style="border:none; border-top:1px solid #e2e8f0; margin:18px 0;">
    <p style="font-size:11px; color:#94a3b8; margin:0;">Čas preizkusa: samodejno sporočilo sistema {APP_TITLE}.</p>
  </div>
</body>
</html>"""
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        server.sendmail(from_addr, [test_recipient], msg.as_string())
        server.quit()
        return True, f"Povezava s strežnikom {host}:{port} je bila uspešna! Testno sporočilo je bilo poslano na {test_recipient}."
    except Exception as exc:
        logger.error("Testna SMTP povezava ni uspela: %s", exc)
        return False, f"Povezava s strežnikom {host}:{port} ni uspela: {exc}"


def send_email(to_email: str, subject: str, body_text: str, body_html: str | None = None, db=None) -> bool:
    """Pošlje e-pošto preko SMTP ali jo varno zabeleži v dnevnik, če SMTP ni nastavljen."""
    to_email = (to_email or "").strip()
    if not to_email or "@" not in to_email:
        logger.warning("Neveljaven prejemnik e-pošte: %r", to_email)
        return False

    cfg = get_smtp_config(db)
    if not cfg["host"]:
        # SMTP ni nastavljen – varno zabeležimo vsebino v lokalni dnevnik brez napake
        tmp_dir = BASE_DIR / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        mail_log = tmp_dir / "mail.log"
        with open(mail_log, "a", encoding="utf-8") as f:
            f.write(f"\n--- {subject} -> {to_email} ---\n{body_text}\n")
        logger.info("SMTP ni konfiguriran. Sporočilo za %s zabeleženo v %s", to_email, mail_log)
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((str(Header(cfg["from_name"], "utf-8")), cfg["from_email"]))
        msg["To"] = to_email

        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        if cfg["security"] == "ssl" or cfg["port"] == 465:
            server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=12)
        else:
            server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=12)
            server.ehlo()
            if cfg["security"] == "tls" or cfg["port"] in (587, 25):
                server.starttls()
                server.ehlo()

        if cfg["user"] and cfg["password"]:
            server.login(cfg["user"], cfg["password"])

        server.sendmail(cfg["from_email"], [to_email], msg.as_string())
        server.quit()
        logger.info("E-pošta uspešno poslana na %s: %s", to_email, subject)
        return True
    except Exception as exc:
        logger.exception("Napaka pri pošiljanju e-pošte na %s: %s", to_email, exc)
        return False


def send_password_reset_email(to_email: str, username: str, reset_url: str, db=None) -> bool:
    """Pripravi in pošlje sporočilo za varno ponastavitev gesla."""
    subject = f"Ponastavitev gesla · {APP_TITLE}"
    body_text = (
        f"Pozdravljeni, {username}!\n\n"
        f"Prejeli smo zahtevo za ponastavitev gesla za vaš račun v aplikaciji {APP_TITLE}.\n\n"
        f"Če ste to zahtevali vi, kliknite na naslednjo povezavo in nastavite novo geslo:\n"
        f"{reset_url}\n\n"
        f"Povezava je veljavna 1 uro. Če zahteve niste oddali vi, to sporočilo preprosto prezrite.\n\n"
        f"Lep pozdrav,\n"
        f"{APP_TITLE}"
    )
    body_html = f"""<!doctype html>
<html lang="sl">
<head><meta charset="utf-8"></head>
<body style="font-family:system-ui,-apple-system,sans-serif; background:#f8fafc; color:#1e293b; padding:24px;">
  <div style="max-width:540px; margin:auto; background:#ffffff; border-radius:8px; border:1px solid #cbd5e1; padding:28px;">
    <h2 style="color:#1e3a8a; margin-top:0;">📚 {APP_TITLE}</h2>
    <p>Pozdravljeni, <strong>{username}</strong>!</p>
    <p>Prejeli smo vaš zahtevek za ponastavitev gesla za vaš račun v aplikaciji <strong>{APP_TITLE}</strong>.</p>
    <p>Za nastavitev novega gesla kliknite na spodnji gumb:</p>
    <div style="text-align:center; margin:24px 0;">
      <a href="{reset_url}" style="background:#2563eb; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:6px; font-weight:bold; display:inline-block;">
        Ponastavi geslo
      </a>
    </div>
    <p style="font-size:12px; color:#64748b;">
      Povezava je veljavna 1 uro. Če zahteve niste sprožili vi, lahko to sporočilo mirno prezrete – vaše geslo ostaja nespremenjeno.
    </p>
    <hr style="border:none; border-top:1px solid #e2e8f0; margin:20px 0;">
    <p style="font-size:11px; color:#94a3b8; margin:0;">
      Če gumb zgoraj ne deluje, kopirajte naslednjo povezavo v brskalnik:<br>
      <a href="{reset_url}" style="color:#2563eb; word-break:break-all;">{reset_url}</a>
    </p>
  </div>
</body>
</html>"""
    return send_email(to_email, subject, body_text, body_html, db=db)


def send_credentials_email(
    to_email: str,
    full_name: str,
    username: str,
    raw_password: str,
    login_url: str,
    db=None,
) -> bool:
    """Pošlje novo ustvarjene ali ponastavljene prijavne podatke na e-pošto uporabnika."""
    subject = f"Vaši prijavni podatki za dostop do knjižnice · {APP_TITLE}"
    body_text = (
        f"Pozdravljeni, {full_name}!\n\n"
        f"Ustvarjen vam je bil račun za vstop v knjižnični sistem {APP_TITLE}.\n\n"
        f"Uporabniško ime: {username}\n"
        f"Začasno geslo:   {raw_password}\n"
        f"Povezava:       {login_url}\n\n"
        f"Iz varnostnih razlogov priporočamo, da po prvi uspešni prijavi geslo zamenjate v svojem profilu.\n\n"
        f"Lep pozdrav,\n"
        f"{APP_TITLE}"
    )
    body_html = f"""<!doctype html>
<html lang="sl">
<head><meta charset="utf-8"></head>
<body style="font-family:system-ui,-apple-system,sans-serif; background:#f8fafc; color:#1e293b; padding:24px;">
  <div style="max-width:540px; margin:auto; background:#ffffff; border-radius:8px; border:1px solid #cbd5e1; padding:28px;">
    <h2 style="color:#1e3a8a; margin-top:0;">📚 {APP_TITLE}</h2>
    <p>Pozdravljeni, <strong>{full_name}</strong>!</p>
    <p>Skrbnik sistema vam je ustvaril ali ponastavil račun za vstop v sistem <strong>{APP_TITLE}</strong>.</p>
    <div style="background:#f1f5f9; border:1px solid #cbd5e1; border-radius:6px; padding:16px; margin:20px 0;">
      <p style="margin:0 0 8px 0;"><strong>Uporabniško ime:</strong> <code style="font-size:14px; background:#fff; padding:3px 8px; border-radius:4px; border:1px solid #cbd5e1;">{username}</code></p>
      <p style="margin:0;"><strong>Začasno geslo:</strong> <code style="font-size:14px; background:#fff; padding:3px 8px; border-radius:4px; border:1px solid #cbd5e1;">{raw_password}</code></p>
    </div>
    <div style="text-align:center; margin:24px 0;">
      <a href="{login_url}" style="background:#2563eb; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:6px; font-weight:bold; display:inline-block;">
        Prijava v knjižnico
      </a>
    </div>
    <p style="font-size:12px; color:#64748b;">
      ⚠️ Iz varnostnih razlogov priporočamo, da po prvi uspešni prijavi geslo nemudoma zamenjate v razdelku <em>Moj profil</em>.
    </p>
    <hr style="border:none; border-top:1px solid #e2e8f0; margin:20px 0;">
    <p style="font-size:11px; color:#94a3b8; margin:0;">
      Povezava za vstop: <a href="{login_url}" style="color:#2563eb;">{login_url}</a>
    </p>
  </div>
</body>
</html>"""
    return send_email(to_email, subject, body_text, body_html, db=db)
