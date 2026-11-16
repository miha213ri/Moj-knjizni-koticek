# 📚 Moj knjižni kotiček

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-red.svg)](https://www.sqlalchemy.org/)
[![Database](https://img.shields.io/badge/Database-MariaDB%20%7C%20SQLite-orange.svg)](https://mariadb.org/)
[![Developed with ChatGPT](https://img.shields.io/badge/Developed%20with-ChatGPT-74aa9c.svg)](https://chatgpt.com/share/6af8b720-f718-83ed-80ae-dea8a4c323ac)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Moj knjižni kotiček** je sodobna, zanesljiva in odzivna spletna aplikacija za celovito vodenje domače ali skupne knjižnice. Omogoča upravljanje fizičnih izvodov knjig na več lokacijah, avtomatsko pridobivanje bibliografskih podatkov preko ISBN iz slovenskih in mednarodnih katalogov (COBISS+, Google Books, Open Library, EMKA.si), evidenco izposoj, družinski bralni dnevnik ter knjižne želje.

Aplikacija je zasnovana za dvojno uporabo:
1. **Lokalno v domačem omrežju** (osebni računalnik poganja SQLite bazo in lokalni strežnik).
2. **Na spletnem gostovanju** (npr. NeoServ cPanel z LiteSpeed / Phusion Passenger in MariaDB).

---

## 🤖 Razvoj s pomočjo umetne inteligence (ChatGPT)

Ta projekt je bil načrtovan, razvit, diagnosticiran in izpopolnjen v tesnem sodelovanju z modelom **ChatGPT** (OpenAI). 

Od začetne ideje in predelave stare namizne kode (PyQt) v sodoben spletni servis FastAPI, do reševanja specifičnih tehničnih izzivov:
- arhitekturna optimizacija za deljeno gostovanje LiteSpeed (WSGI/ASGI preko `a2wsgi` in Passenger),
- odprava zapletov s kodiranjem znakov in slovenskimi šumniki (`utf8mb4_unicode_ci`),
- shranjevanje in optimizacija naslovnic neposredno v bazi (`MEDIUMBLOB`),
- 4-stopenjski sistem uporabniških pravic (RBAC: `ADMIN`, `EDITOR`, `USER`, `GUEST`),
- zaščita pred brute-force napadi s samodejnim zaklepanjem in možnostjo takojšnje odjave vseh naprav,
- varen uvoz iz preglednic Excel z izoliranimi transakcijskimi savepointi.

Celoten potek pogovora, navodil, arhitekturnih odločitev in iterativnega razvoja si lahko ogledate v javno deljenem pogovoru:
👉 **[Ogled celotnega ChatGPT pogovora o razvoju knjižnice](https://chatgpt.com/share/6af8b720-f718-83ed-80ae-dea8a4c323ac)**

---

## ✨ Glavne funkcionalnosti

### 📖 Katalog knjig in večkriterijsko iskanje
- **Dva načina prikaza:** Preklop med vizualnim kartičnim pogledom z naslovnicami (**KARTICE**) in pregledno tabelo (**SEZNAM**).
- **Razvrščanje:** Urejanje po inventarni številki, naslovu, avtorjih, letu, ISBN, žanru, zbirki, lokaciji, stanju ter statusu.
- **Hitro iskanje:** Iskanje po vseh bibliografskih poljih, vključno z opombami in povzetkom.
- **Izvoz v Excel:** Trenutno filtrirane in razvrščene zadetke lahko z enim klikom izvozite v Excel (`.xlsx`).

### 🔎 Samodejno prepoznavanje knjig (ISBN Lookup)
- Ob vnosu ISBN številke aplikacija samodejno poišče podatke v zunanjih virih:
  - **COBISS+** (slovenski knjižnični katalog)
  - **Open Library**
  - **Google Books**
  - **EMKA.si** (slovenske izdaje)
- Samodejni prenos in lokalna optimizacija naslovnice (preverjanje veljavnosti s Pillow, EXIF avtorotacija, pretvorba v WebP).

### 🖼️ Množični uvoz naslovnic
- Preko zavihka *Nastavitve* lahko naenkrat naložite do 50 slikovnih datotek (JPG, PNG, WEBP).
- Sistem slike avtomatsko poveže s pravo knjigo na podlagi imena datoteke:
  - npr. `K-000123.jpg` (ujemanje po inventarni številki) ali
  - `9789610000000.jpg` (ujemanje po ISBN, kadar pripada enemu izvodu).

### 🏢 Več fizičnih knjižnic / lokacij
- Podpora za več ločenih knjižnic (npr. *Domača knjižnica*, *Vikend*, *Pisarna*).
- Katalog je skupen za pregledovanje, urejanje in izposoja pa sta omejeni na uporabnikove dodeljene lokacije.
- Hierarhično določanje lokacije knjige: **Soba ➔ Omara ➔ Polica**.

### 👥 Uporabniški računi, varnost in vloge (RBAC)
- **Štiri ravni dostopa:**
  - `ADMIN`: Popoln nadzor nad vsemi lokacijami, uporabniškimi računi, sistemskimi nastavitvami, revizijsko sledjo in varnostnimi kopijami.
  - `EDITOR`: Polne pravice urejanja knjižničnega gradiva (dodajanje, urejanje, brisanje knjig, vodenje izposoj) v dodeljenih lokacijah; nima dostopa do administracije.
  - `USER`: Redni uporabnik: pregled kataloga, dodajanje na seznam želja, osebni bralni dnevnik.
  - `GUEST`: Samo branje (Read-Only) – vsakršen vnos ali izposoja je strežniško zavrnjena (HTTP 403).
- **Varnostni mehanizmi:**
  - Varno zgoščevanje gesel s kriptografsko funkcijo `scrypt` z naključno soljo in strogo preverjanje moči (najmanj 12 znakov ter obvezna številka ali posebni znak).
  - Dinamično upravljanje SMTP e-poštnega strežnika preko skrbniške nadzorne plošče (shramba v tabeli `app_settings` z varnostnim zaledjem v `.env`, podpora za SSL 465 in STARTTLS 587 ter orodje za takojšen preizkus povezave s testnim sporočilom).
  - Samodejno pošiljanje prijavnih podatkov (uporabniško ime in novo/začasno geslo) na e-pošto ob ustvarjanju računa ali administratorski ponastavitvi gesla.
  - Zaščita pred napadi s surovo silo (Brute-force): po 5 neuspelih poskusih se račun začasno zaklene; možnost administratorskega odklepa z enim klikom.
  - Pozabljeno geslo in ponastavitev prek e-pošte z enkratnim časovno omejenim žetonom.
  - Upravljanje sej in možnost takojšnje odjave vseh naprav (`session_version`).
  - Podpisani sejni piškotki (`HttpOnly`, `SameSite=Lax`, `Secure` za HTTPS).
  - Varnostne HTTP glave (`X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-XSS-Protection: 1; mode=block`).
  - Zasebnost: `/robots.txt` (`Disallow: /`) in meta oznake `noindex, nofollow`.
  - GDPR: Izključno tehnično nujni sejni piškotki brez vsakršnega sledenja ali analitike.

### 📤 Izposojevalci in vodenje izposoj
- Evidenca izposojenih knjig osebam z avtomatskim rokom vračila (privzeto 30 dni, nastavljivo).
- Zgodovina preteklih izposoj za vsak fizični izvod knjige posebej.
- Hitro označevanje vrnjenih knjig.

### ⭐ Družinski bralni dnevnik in seznam želja
- Vsak družinski član ima svoj osebni profil.
- Bralni dnevnik omogoča beleženje vseh prebranih knjig (tudi tistih, ki niso del domače zbirke, npr. izposojenih v mestni knjižnici).
- Seznam želja za načrtovane nakupe in priporočila.

### 💾 Zanesljive varnostne kopije in obnova
- Celovit izvoz baze podatkov skupaj z vsemi naslovnicami v enem stisnjenem arhivu ZIP (`database.json` + `manifest.json`) ali `JSON.GZ`.
- Varna obnova znotraj transakcije z začasnim izklopom preverjanja tujih ključev.

---

## 🏗️ Tehnološki sklad

- **Programski jezik:** Python 3.11+ (priporočeno 3.13)
- **Spletni ogrodji:** [FastAPI](https://fastapi.tiangolo.com/) & [Starlette](https://www.starlette.io/)
- **Predloge (Templates):** [Jinja2](https://jinja.palletsprojects.com/)
- **ORM in podatkovna baza:** [SQLAlchemy 2.0](https://www.sqlalchemy.org/) z gonilnikom [PyMySQL](https://github.com/PyMySQL/PyMySQL) (MariaDB) ali SQLite
- **Deljeno gostovanje WSGI/ASGI:** [a2wsgi](https://github.com/abersheeran/a2wsgi) & Phusion Passenger (LiteSpeed)
- **Obdelava slik:** [Pillow](https://python-pillow.org/) (rotacija, WebP stiskanje)
- **Uvoz/Izvoz Excel:** [openpyxl](https://openpyxl.readthedocs.io/)
- **HTTP odjemalec:** [httpx](https://www.python-httpx.org/)

---

## 🚀 Hitri začetek (Lokalno poganjanje)

### 1. Kloniranje repozitorija
```bash
git clone https://github.com/miha213ri/Moj-knjizni-koticek.git
cd moj-knjizni-koticek
```

### 2. Namestitev virtualnega okolja
- **Windows:**
  ```cmd
  py -3 -m venv .venv
  .venv\Scripts\activate
  ```
- **Linux / macOS:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 3. Namestitev odvisnosti
```bash
pip install --upgrade pip
pip install -r requirements-dev.txt
```

### 4. Priprava konfiguracije
Kopirajte `.env.example` v `.env`:
- Windows: `copy .env.example .env`
- Linux/macOS: `cp .env.example .env`

### 5. Ustvarjanje skrbnika (Administratorja)
V datoteko `.env` začasno dodajte podatke:
```ini
BOOTSTRAP_LOCATION_NAME=Domača knjižnica
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_DISPLAY_NAME=Skrbnik
BOOTSTRAP_ADMIN_PASSWORD=VarnoGeslo1234#
```
Nato zaženite:
```bash
python scripts/create_admin.py
```

### 6. Zagon avtomatiziranih testov
```bash
python tests/test_full_suite.py
```

### 7. Zagon programa
```bash
python run.py
```
Aplikacijo odprite v brskalniku na **http://127.0.0.1:8000**.

---

## 🌐 Namestitev na deljeno gostovanje (NeoServ / cPanel)

Podrobna navodila za postavitev na NeoServ LiteSpeed gostovanje s Phusion Passenger in MariaDB najdete v namenskem dokumentu:
👉 **[Podrobna navodila za namestitev (NAVODILA_NAMESTITEV.md)](NAVODILA_NAMESTITEV.md)**

---

## 📁 Struktura projekta

```text
moj-knjizni-koticek/
├── app/                        # Glavni programski paket
│   ├── routes/                 # FastAPI usmerjevalniki (Endpoints)
│   │   ├── admin.py            # Nadzorna plošča, uporabniki, nastavitve, revizijska sled
│   │   ├── auth.py             # Prijava, registracija, profil, ponastavitev gesel
│   │   ├── backup.py           # Izvoz in obnova baze
│   │   ├── books.py            # Katalog, pregled, dodajanje, brisanje
│   │   ├── borrowers.py        # Upravljanje izposojevalcev
│   │   ├── library_api.py      # Pomožni API klici
│   │   ├── loans.py            # Prikaz izposojenih knjig
│   │   ├── loan_actions.py     # Akcije izposoje in vračila
│   │   ├── readings_wishes.py  # Bralni dnevnik in seznam želja
│   │   └── settings.py         # Nastavitve, uvoz Excel in množični uvoz slik
│   ├── static/                 # Statične datoteke (CSS, JavaScript, SVG)
│   │   ├── app.js              # Klientna interaktivnost
│   │   ├── no_cover.svg        # Privzeta nadomestna slika za naslovnico
│   │   └── style.css           # Odzivna grafična podoba
│   ├── templates/              # Jinja2 HTML predloge
│   ├── access.py               # Preverjanje pravic in vlog (RBAC) ter dostopa do lokacij
│   ├── audit.py                # Pomožne funkcije za revizijsko sledenje
│   ├── catalog.py              # Iskanje v COBISS+, Google Books, Open Library, EMKA
│   ├── config.py               # Nalaganje konfiguracije in .env
│   ├── database.py             # Povezava SQLAlchemy in SessionLocal
│   ├── import_export.py        # Logika za uvoz in izvoz preglednic Excel
│   ├── mailer.py               # Pošiljanje e-poštnih sporočil (SMTP z varnim lokalnim beleženjem)
│   ├── main.py                 # FastAPI aplikacija in varnostni middleware
│   ├── migrations.py           # Samodejne migracije sheme brez izgube podatkov
│   ├── models.py               # Podatkovni modeli SQLAlchemy
│   ├── route_helpers.py        # Pomožne funkcije za renderiranje
│   ├── runtime_context.py      # Globalni kontekst predlog
│   ├── security.py             # Zgoščevanje gesel s scrypt
│   ├── server_backup.py        # Serializacija in obnova arhivov baze
│   ├── services.py             # Skupne poslovne funkcije kataloga
│   └── templating.py           # Jinja2 konfiguracija
├── scripts/                    # Skripte za skrbnike in vzdrževanje
│   ├── check_database.py       # Preizkus povezave z bazo podatkov
│   ├── create_admin.py         # Ustvarjanje prvega administratorja
│   ├── diagnose_mariadb_encoding.py  # Diagnostika UTF-8 / šumnikov
│   └── verify_project.py       # Preverjanje celovitosti namestitve
├── tests/                      # Avtomatizirani testi
│   └── test_full_suite.py      # Celovita zbirka 9 testnih sklopov (vključno z SMTP in prijavnimi podatki)
├── .env.example                # Vzorec varnih nastavitev
├── .gitignore                  # Pravila za izločitev zasebnih datotek
├── CHANGELOG.md                # Zgodovina vseh sprememb in izdaj
├── LICENSE                     # Licenca MIT
├── NAVODILA_NAMESTITEV.md      # Podrobna navodila za lokalni in strežniški zagon
├── passenger_wsgi.py           # Vstopna točka za LiteSpeed / Passenger
├── PODATKOVNA_ARHITEKTURA.md   # Opis sheme in arhitekture podatkovne baze
├── predloga_knjige.xlsx        # Vzorec Excel preglednice za uvoz knjig
├── requirements.txt            # Produkcijske odvisnosti (Python 3.13)
├── requirements-dev.txt        # Razvojne odvisnosti (vključuje Uvicorn)
└── run.py                      # Lokalni zaganjalnik
```

---

## 📄 Licenca

Projekt je licenciran pod odprtokodno licenco **[MIT License](LICENSE)**. Uporaba, spreminjanje in prilagajanje kode so prosto dovoljeni z navedbo avtorstva.
