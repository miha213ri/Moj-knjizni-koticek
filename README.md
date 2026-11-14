# 📚 Moj knjižni kotiček

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-red.svg)](https://www.sqlalchemy.org/)
[![Database](https://img.shields.io/badge/Database-MariaDB%20%7C%20SQLite-orange.svg)](https://mariadb.org/)
[![Developed with ChatGPT](https://img.shields.io/badge/Developed%20with-ChatGPT-74aa9c.svg)](https://chatgpt.com/share/6af8b720-f718-83ed-80ae-dea8a4c323ac)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Moj knjižni kotiček** je sodobna spletna aplikacija za celovito vodenje domače in družinske knjižnice. Omogoča upravljanje fizičnih izvodov knjig na več lokacijah, avtomatsko pridobivanje podatkov preko ISBN iz slovenskih in mednarodnih katalogov (COBISS+, Google Books, Open Library, EMKA.si), vodenje izposoj, bralni dnevnik ter knjižne želje.

Aplikacija je zasnovana za dvojno uporabo:
1. **Lokalno v domačem omrežju** (računalnik poganja SQLite bazo in lokalni strežnik).
2. **Na spletnem gostovanju** (npr. NeoServ cPanel z LiteSpeed / Phusion Passenger in MariaDB).

---

## 🤖 Razvoj s pomočjo umetne inteligence (ChatGPT)

Ta projekt je bil v celoti načrtovan, razvit, diagnosticiran in izpopolnjen v sodelovanju z modelom **ChatGPT** (OpenAI). 

Od začetne ideje in predelave stare namizne kode (PyQt6) v sodoben FastAPI spletni servis, do reševanja specifičnih izzivov:
- optimizacija delovanja na deljenem gostovanju LiteSpeed (WSGI/ASGI preko 2wsgi in Passenger),
- odprava težav s kodiranjem znakov in slovenskimi šumniki (utf8mb4_unicode_ci),
- shranjevanje in optimizacija naslovnic neposredno v bazi (MEDIUMBLOB),
- napredno kaskadno brisanje in izolirani transakcijski uvoz iz preglednic Excel.

Celoten potek pogovora, navodil, arhitekturnih odločitev in iterativnega razvoja si lahko ogledate v javno deljenem pogovoru:
👉 **[Ogled celotnega ChatGPT pogovora o razvoju knjižnice](https://chatgpt.com/share/6af8b720-f718-83ed-80ae-dea8a4c323ac)**

---

## ✨ Glavne funkcionalnosti

### 📖 Katalog knjig in večkriterijsko iskanje
- **Dva načina prikaza:** Preklop med vizualnim kartičnim pogledom z naslovnicami (KARTICE) in pregledno tabelo (SEZNAM).
- **Razvrščanje:** Urejanje po inventarni številki, naslovu, avtorjih, letu, ISBN, žanru, zbirki, lokaciji, stanju ter statusu.
- **Hitro iskanje:** Iskanje po vseh bibliografskih poljih, vključno z opombami in povzetkom.
- **Izvoz v Excel:** Trenutno filtrirane in razvrščene zadetke lahko z enim klikom izvozite v Excel (.xlsx).

### 🔎 Samodejno prepoznavanje knjig (ISBN Lookup)
- Ob vnosu ISBN številke aplikacija samodejno poišče podatke v zunanjih virih:
  - **COBISS+** (slovenski knjižnični katalog)
  - **Open Library**
  - **Google Books**
  - **EMKA.si** (slovenske izdaje)
- Samodejni prenos in lokalna optimizacija naslovnice (preverjanje formata, EXIF rotacija, pretvorba v WebP do 1200×1700).

### 🖼️ Množični uvoz naslovnic
- Preko zavihka *Nastavitve* lahko naenkrat naložite do 50 slikovnih datotek (JPG, PNG, WEBP).
- Sistem slike avtomatsko poveže s pravo knjigo na podlagi imena datoteke:
  - npr. K-000123.jpg (ujemanje po inventarni številki) ali
  - 9789610000000.jpg (ujemanje po ISBN, kadar pripada enemu izvodu).
- Zaščita pred dvoumnostjo in možnost izbire prepisa obstoječih slik.

### 🏢 Več fizičnih knjižnic / lokacij
- Podpora za več ločenih knjižnic (npr. *Domača knjižnica*, *Vikend*, *Pisarna*).
- Katalog je skupen za pregledovanje, urejanje in izposoja pa sta omejeni na uporabnikove dodeljene lokacije.
- Hierarhično določanje lokacije knjige: **Soba ➔ Omara ➔ Polica**.

### 👥 Uporabniški računi in varnost
- Dve ravni uporabnikov:
  - ADMIN: popoln nadzor nad vsemi lokacijami, uporabniki, uvozom in varnostnimi kopijami.
  - USER: urejanje knjig in izposoj znotraj lastnih dodeljenih lokacij.
- Kriptografsko varno zgoščevanje gesel s funkcijo scrypt.
- Podpisane seje s podporo za HTTPS piškotke.

### 📤 Izposojevalci in vodenje izposoj
- Evidenca izposojenih knjig zunanjim osebam z avtomatskim rokom vračila (privzeto 30 dni).
- Zgodovina preteklih izposoj za vsak fizični izvod knjige posebej.
- Hitro označevanje vrnjenih knjig.

### ⭐ Družinski bralni dnevnik in seznam želja
- Vsak družinski član ima svoj osebni profil.
- Bralni dnevnik omogoča beleženje vseh prebranih knjig (tudi tistih, ki niso del domače zbirke, npr. izposojenih v mestni knjižnici).
- Seznam želja za načrtovane nakupe in priporočila.

### 💾 Zanesljive varnostne kopije in obnova
- Celovit izvoz celotne baze podatkov skupaj z vsemi naslovnicami v enem stisnjenem arhivu ZIP (database.json + manifest.json) ali JSON.GZ.
- Varna obnova znotraj podatkovne transakcije.

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
`ash
git clone https://github.com/UPORABNIK/moj-knjizni-koticek.git
cd moj-knjizni-koticek
`

### 2. Namestitev virtualnega okolja
- **Windows:**
  `cmd
  py -3 -m venv .venv
  .venv\Scripts\activate
  `
- **Linux / macOS:**
  `ash
  python3 -m venv .venv
  source .venv/bin/activate
  `

### 3. Namestitev odvisnosti
`ash
pip install --upgrade pip
pip install -r requirements-dev.txt
`

### 4. Priprava konfiguracije
Kopirajte .env.example v .env:
- Windows: copy .env.example .env
- Linux/macOS: cp .env.example .env

### 5. Ustvarjanje skrbnika (Administratorja)
V datoteko .env začasno dodajte podatke:
`ini
BOOTSTRAP_LOCATION_NAME=Domača knjižnica
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_DISPLAY_NAME=Skrbnik
BOOTSTRAP_ADMIN_PASSWORD=VarnoGeslo1234#
`
Nato zaženite:
`ash
python scripts/create_admin.py
`

### 6. Zagon programa
`ash
python run.py
`
Aplikacijo odprite v brskalniku na **http://127.0.0.1:8000**.

---

## 🌐 Namestitev na deljeno gostovanje (NeoServ / cPanel)

Podrobna navodila za postavitev na NeoServ LiteSpeed gostovanje s Phusion Passenger in MariaDB najdete v namenskem dokumentu:
👉 **[Podrobna navodila za namestitev (NAVODILA_NAMESTITEV.md)](NAVODILA_NAMESTITEV.md)**

---

## 📁 Struktura projekta

`	ext
moj-knjizni-koticek/
├── app/                        # Glavni programski paket
│   ├── routes/                 # FastAPI usmerjevalniki (Endpoints)
│   │   ├── admin.py            # Upravljanje uporabnikov in lokacij
│   │   ├── auth.py             # Prijava in odjava
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
│   ├── access.py               # Preverjanje pravic in dostopa do lokacij
│   ├── catalog.py              # Iskanje v COBISS+, Google Books, Open Library, EMKA
│   ├── config.py               # Nalaganje konfiguracije in .env
│   ├── database.py             # Povezava SQLAlchemy in SessionLocal
│   ├── import_export.py        # Logika za uvoz in izvoz preglednic Excel
│   ├── main.py                 # FastAPI aplikacija in varnostni middleware
│   ├── models.py               # Podatkovni modeli SQLAlchemy
│   ├── route_helpers.py        # Pomožne funkcije za renderiranje
│   ├── security.py             # Zgoščevanje gesel s scrypt
│   ├── server_backup.py        # Serializacija in obnova arhivov baze
│   └── services.py             # Skupne poslovne funkcije kataloga
├── scripts/                    # Skripte za skrbnike in vzdrževanje
│   ├── check_database.py       # Preizkus povezave z bazo podatkov
│   ├── create_admin.py         # Ustvarjanje prvega administratorja
│   ├── diagnose_mariadb_encoding.py  # Diagnostika UTF-8 / šumnikov
│   └── verify_project.py       # Preverjanje celovitosti namestitve
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
`

---

## 📄 Licenca

Projekt je licenciran pod odprtokodno licenco **[MIT License](LICENSE)**. Uporaba, spreminjanje in prilagajanje kode so prosto dovoljeni z navedbo avtorstva.