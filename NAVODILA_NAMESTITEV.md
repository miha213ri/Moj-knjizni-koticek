# Navodila za namestitev in zagon – Moj knjižni kotiček

Aplikacija **Moj knjižni kotiček** je zasnovana tako, da deluje v dveh načinih:
1. **Lokalni način (Razvoj ali domača uporaba):** Hitri zagon z vgrajeno bazo SQLite brez potrebe po zunanjem strežniku.
2. **Produkcijski način (Deljeno gostovanje cPanel / LiteSpeed, npr. NeoServ):** Delovanje z bazo MariaDB/MySQL in WSGI strežnikom Phusion Passenger.

---

## 1. Lokalna namestitev (Windows, Linux, macOS)

### Zahteve
- Python 3.11, 3.12, 3.13 ali 3.14 (priporočeno 3.13+)
- Spletni brskalnik

### Postopek po korakih

1. **Prenos kode ali kloniranje repozitorija:**
   ```bash
   git clone https://github.com/miha213ri/Moj-knjizni-koticek.git
   cd moj-knjizni-koticek
   ```

2. **Ustvarjanje virtualnega okolja:**
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

3. **Namestitev programskih knjižnic:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements-dev.txt
   ```
   *(Opomba: requirements-dev.txt vključuje razvojni strežnik uvicorn.)*

4. **Priprava konfiguracije .env:**
   Kopiraj `.env.example` v `.env`:
   - **Windows:** `copy .env.example .env`
   - **Linux / macOS:** `cp .env.example .env`
   *(Za lokalni razvoj privzete nastavitve delujejo takoj. Aplikacija bo avtomatsko ustvarila lokalno datoteko baze `local_library.db`.)*

5. **Ustvarjanje prvega skrbniškega računa (Administrator):**
   V datoteko `.env` dodaj začasne podatke:
   ```ini
   BOOTSTRAP_LOCATION_NAME=Domača knjižnica
   BOOTSTRAP_ADMIN_USERNAME=admin
   BOOTSTRAP_ADMIN_DISPLAY_NAME=Skrbnik
   BOOTSTRAP_ADMIN_PASSWORD=VarnoGeslo1234#
   ```
   Nato v terminalu zaženi:
   ```bash
   python scripts/create_admin.py
   ```
   Skripta bo pripravila tabele v bazi, ustvarila skrbnika in samodejno počistila začasne podatke iz `.env`.

6. **Zagon avtomatiziranih testov:**
   ```bash
   python tests/test_full_suite.py
   ```
   Zagon preveri vseh 9 ključnih podsistemov aplikacije (avtentikacijo, moč gesel, zaklepanje računov, ponastavitev gesel, seje, pravice vlog, katalog, izposoje, Excel izvoz, obnovo varnostnih kopij ter SMTP nastavitve in pošiljanje prijavnih podatkov).

7. **Zagon aplikacije:**
   ```bash
   python run.py
   ```
   Odpri brskalnik na **http://127.0.0.1:8000**.

---

## 2. Namestitev na deljeno gostovanje (NeoServ / cPanel z LiteSpeed in Passenger)

### 1. Priprava baze MariaDB v cPanelu
1. V cPanelu odpri razdelek **MySQL® Databases** (ali Čarovnik za baze podatkov).
2. Ustvari novo bazo podatkov (npr. `uporabnik_knjiznica`).
3. Ustvari novega uporabnika baze z močnim geslom.
4. Uporabniku dodeli **vse pravice** (*ALL PRIVILEGES*) nad ustvarjeno bazo.
5. V orodju **phpMyAdmin** preveri, da je privzeto kodiranje baze `utf8mb4_unicode_ci`.

### 2. Ustvarjanje Python aplikacije v cPanelu (Setup Python App)
1. V cPanelu poišči **Setup Python App** (Phusion Passenger).
2. Klikni **Create Application**:
   - **Python version:** Izberi 3.13 ali 3.12.
   - **Application root:** `moj-knjizni-koticek` (ali pot do mape na strežniku).
   - **Application URL:** Izberi domeno ali poddomeno (npr. `knjiznica.tvojadomena.si`).
   - **Application startup file:** `passenger_wsgi.py`.
   - **Application Entry point:** `application`.
3. Klikni **Create**.

### 3. Prenos datotek na strežnik
Naloži vsebino repozitorija v mapo aplikacije (prek FTP, Git ali cPanel Upravitelja datotek - *File Manager*).
*(Pazi, da v korenski mapi ostane `passenger_wsgi.py`.)*

### 4. Nastavitev .env na strežniku
Ustvari datoteko `.env` v korenski mapi aplikacije in vpiši:
```ini
APP_ENV=production
APP_SECRET_KEY=zgeneriraj-svoj-dolg-nakljucni-kljuc-vsaj-40-znakov
SESSION_HTTPS_ONLY=1

DB_HOST=localhost
DB_PORT=3306
DB_NAME=uporabnik_knjiznica
DB_USER=uporabnik_knjiznicar
DB_PASSWORD=tvoje_mocno_geslo_baze

# E-pošta (SMTP za ponastavitev gesel in pošiljanje prijavnih podatkov)
# (Opomba: SMTP nastavitve lahko kasneje kadarkoli vnesete ali spremenite tudi neposredno v skrbniškem vmesniku /admin)
SMTP_HOST=mail.tvojadomena.si
SMTP_PORT=587
SMTP_USER=knjiznica@tvojadomena.si
SMTP_PASSWORD=geslo_predala
SMTP_FROM=knjiznica@tvojadomena.si
SMTP_TLS=1

REGISTRATION_ENABLED=1
DEFAULT_LOAN_DAYS=30
```

### 5. Namestitev knjižnic in inicializacija skrbnika
V cPanelu v vmesniku *Setup Python App* prekopiraj ukaz za aktivacijo virtualnega okolja (npr. `source /home/uporabnik/virtualenv/.../activate`) in ga zaženi v SSH terminalu:
```bash
pip install --upgrade pip
pip install -r requirements.txt
python scripts/create_admin.py
```

### 6. Ponovni zagon aplikacije
V cPanelu pod *Setup Python App* klikni gumb **Restart Application**. Aplikacija je pripravljena za uporabo na tvoji domeni!

---

## 3. Varnostna opozorila in priporočila

- **HTTPS certifikat:** V produkciji vedno uporabljaj veljaven SSL certifikat (npr. brezplačni Let's Encrypt prek cPanela) in imej vključeno `SESSION_HTTPS_ONLY=1`.
- **Zasebnost:** Aplikacija ima v `/robots.txt` nastavljeno prepoved indeksiranja (`Disallow: /`), saj gre za zasebno družinsko ali skupno knjižnico.
- **Varnostne kopije:** Redno prenašaj arhive varnostnih kopij prek zavihka *Nastavitve -> Varnostne kopije* (arhiv `.zip` vsebuje vse relacijske tabele in vse slike naslovnic v obliki `MEDIUMBLOB`).
