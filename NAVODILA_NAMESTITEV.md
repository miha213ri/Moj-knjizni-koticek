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
   `ash
   git clone https://github.com/UPORABNIK/moj-knjizni-koticek.git
   cd moj-knjizni-koticek
   `

2. **Ustvarjanje virtualnega okolja:**
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

3. **Namestitev programskih knjižnic:**
   `ash
   pip install --upgrade pip
   pip install -r requirements-dev.txt
   `
   *(Opomba: equirements-dev.txt vključuje razvojni strežnik uvicorn.)*

4. **Priprava konfiguracije .env:**
   Kopiraj .env.example v .env:
   - **Windows:**
     `cmd
     copy .env.example .env
     `
   - **Linux / macOS:**
     `ash
     cp .env.example .env
     `
   *(Za lokalni razvoj privzete nastavitve delujejo takoj. Aplikacija bo avtomatsko ustvarila lokalno datoteko baze local_library.db.)*

5. **Ustvarjanje prvega skrbniškega računa (Administrator):**
   V datoteko .env dodaj začasne podatke:
   `ini
   BOOTSTRAP_LOCATION_NAME=Domača knjižnica
   BOOTSTRAP_ADMIN_USERNAME=admin
   BOOTSTRAP_ADMIN_DISPLAY_NAME=Skrbnik
   BOOTSTRAP_ADMIN_PASSWORD=VarnoGeslo1234#
   `
   Nato v terminalu zaženi:
   `ash
   python scripts/create_admin.py
   `
   Skripta bo pripravila tabele v bazi, ustvarila skrbnika in samodejno počistila začasne podatke iz .env.

6. **Zagon aplikacije:**
   `ash
   python run.py
   `
   Odpri brskalnik na: **http://127.0.0.1:8000** in se prijavi s svojim računom.

---

## 2. Produkcijska namestitev na NeoServ (cPanel / LiteSpeed)

NeoServ uporablja spletni strežnik LiteSpeed z vtičnikom Phusion Passenger, ki aplikacijo poganja preko WSGI vmesnika (passenger_wsgi.py).

### Korak 1: Priprava baze podatkov v cPanelu
1. V cPanelu odpri **MySQL® Database Wizard** (ali *Podatkovne zbirke MySQL*).
2. Ustvari novo bazo (npr. uporabnik_knjiznica).
3. Ustvari novega uporabnika baze (npr. uporabnik_knjiznicar) z močnim geslom.
4. Uporabniku dodeli **vse pravice** (*ALL PRIVILEGES*) nad ustvarjeno bazo.
5. V orodju *phpMyAdmin* se prepričaj, da je privzeta primerjava znakov baze nastavljena na **utf8mb4_unicode_ci**.

### Korak 2: Ustvarjanje Python aplikacije v cPanelu
1. V cPanelu odpri **Software > Setup Python App**.
2. Klikni **Create Application**:
   - **Python version:** 3.13.x (ali najnovejša stabilna podprta)
   - **Application root:** knjiznica_app *(mapa naj bo zunaj mape public_html!)*
   - **Application URL:** izberi svojo želeno domeno ali poddomeno (npr. knjiznica.tvojadomena.si)
   - **Application startup file:** pusti privzeto/prazno
   - **Application Entry point:** pusti privzeto/prazno
3. Klikni **CREATE**.
   *(cPanel bo ustvaril mapo knjiznica_app, virtualno okolje in testni passenger_wsgi.py.)*

### Korak 3: Nalaganje programske kode
1. Na vrhu strani *Setup Python App* si kopiraj ukaz za aktivacijo virtualnega okolja (npr. source /home/uporabnik/virtualenv/knjiznica_app/3.13/bin/activate).
2. V cPanel File Managerju odpri mapo knjiznica_app.
3. Naloži vsebino repozitorija (npr. ZIP arhiv) neposredno v knjiznica_app.
4. Prepiši testni passenger_wsgi.py z datoteko iz repozitorija.
5. Preveri, da se v mapi nahajajo:
   - passenger_wsgi.py
   - equirements.txt
   - .env.example
   - mapa pp/
   - mapa scripts/

### Korak 4: Priprava produkcijske datoteke .env
1. V mapi knjiznica_app ustvari datoteko .env (npr. z ukazom ali kopiranjem .env.example).
2. Uredi .env in vpiši:
   `ini
   APP_ENV=production
   APP_SECRET_KEY=TUKAJ_VNESI_NAKLJUCNI_NIZ_NAJMANJ_40_ZNAKOV
   SESSION_HTTPS_ONLY=1

   DB_HOST=localhost
   DB_PORT=3306
   DB_NAME=uporabnik_knjiznica
   DB_USER=uporabnik_knjiznicar
   DB_PASSWORD=TvojeVarnoGesloBazeIzKoraka1

   # Začasno za prvi zagon administratorja:
   BOOTSTRAP_LOCATION_NAME=Glavna knjižnica
   BOOTSTRAP_ADMIN_USERNAME=admin
   BOOTSTRAP_ADMIN_DISPLAY_NAME=Administrator
   BOOTSTRAP_ADMIN_PASSWORD=TvojeVarnoAdminGeslo1234#
   `
   *Skrivni ključ APP_SECRET_KEY lahko ustvariš v cPanel terminalu z:*
   `ash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   `

### Korak 5: Namestitev knjižnic in inicializacija baze
V cPanel **Terminalu** izvedi:
`ash
# 1. Aktiviraj virtualno okolje (uporabi svoj točen ukaz iz cPanela):
source /home/UPORABNIK/virtualenv/knjiznica_app/3.13/bin/activate

# 2. Premakni se v mapo aplikacije:
cd ~/knjiznica_app

# 3. Namesti odvisnosti za produkcijo:
pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt

# 4. Ustvari tabele in prvega administratorja:
python scripts/create_admin.py

# 5. Preveri povezavo z bazo:
python scripts/check_database.py
`

### Korak 6: Ponovni zagon in prijava
1. V cPanelu pojdite na **Setup Python App** in pri svoji aplikaciji kliknite **Restart** (ali v terminalu ustvarite 	mp/restart.txt: 	ouch tmp/restart.txt).
2. Odprite svojo poddomeno v brskalniku (npr. https://knjiznica.tvojadomena.si).
3. Prijavite se z uporabniškim imenom in geslom administratorja, ki ste ga določili v 4. koraku.

---

## 3. Varnostna priporočila

1. **Zaščita .env:** Datoteka .env vsebuje geslo za bazo in skrivni ključ seje. Nikoli je ne nalagajte v javne repozitorije in je ne shranjujte v mapo public_html.
2. **HTTPS:** V produkciji obvezno omogočite SSL certifikat (npr. brezplačni Let's Encrypt v cPanelu) in nastavite SESSION_HTTPS_ONLY=1.
3. **Gesla:** Vsa uporabniška gesla se v bazi shranjujejo s kriptografsko funkcijo scrypt.
4. **Varnostne kopije:** Kot administrator redno izvajajte prenos varnostnih kopij baze preko vgrajene funkcije v zavihku *Upravljanje / Nastavitve*.