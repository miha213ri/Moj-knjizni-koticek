# Dnevnik sprememb (Changelog)

Vse pomembne spremembe v projektu **Moj knjižni kotiček** so zabeležene v tej datoteki.

Format temelji na [Keep a Changelog](https://keepachangelog.com/sl/1.0.0/), projekt pa sledi [Semantičnemu verzijskemu označevanju](https://semver.org/).

---

## [1.0.0] – 2026-11-14

### Uradna stabilna izdaja (Production Release)
Ta izdaja predstavlja prelomno preobrazbo aplikacije iz lokalnega namiznega orodja v sodobno večuporabniško spletno aplikacijo, pripravljeno za deljeno gostovanje (LiteSpeed / Passenger WSGI) ter lokalno uporabo.

Projekt je bil razvit in izpopolnjen v tesnem sodelovanju z umetno inteligenco **ChatGPT** (OpenAI). Celoten potek načrtovanja, diagnostike in iterativnega razvoja je dokumentiran v [deljenem pogovoru ChatGPT](https://chatgpt.com/share/6af8b720-f718-83ed-80ae-dea8a4c323ac).

### Dodano (Added)
- **Strežniška arhitektura FastAPI:**
  - Podpora za produkcijsko poganjanje preko LiteSpeed / cPanel z passenger_wsgi.py in 2wsgi adapterjem.
  - Podpora za lokalni razvoj preko un.py (Uvicorn).
- **Podpora za podatkovne baze:**
  - Polna podpora za MariaDB / MySQL s PyMySQL gonilnikom.
  - Samodejni preklop na lokalno SQLite bazo, kadar strežniška baza ni nastavljena.
  - Optimiziran bazni bazen (connection pool pre-ping, recycle) za stabilno delovanje na deljenem gostovanju.
- **Avtentikacija in večuporabniški sistem:**
  - Prijavni sistem z varno šifriranimi gesli (scrypt).
  - Dve ravni pravic: ADMIN (popoln nadzor nad uporabniki, lokacijami in varnostnimi kopijami) in USER (urejanje dodeljenih lokacij).
  - Podpora za več fizičnih knjižnic/lokacij (npr. domača knjižnica, vikend, pisarna) s skupnim katalogom.
- **Katalog knjig in napredno brskanje:**
  - Preklop med kartičnim (KARTICE) in tabelaričnim (SEZNAM) pogledom.
  - Razvrščanje po vseh ključnih stolpcih (inventarna št., naslov, avtorji, leto, ISBN, žanr, zbirka, lokacija, stanje, status).
  - Izvoz trenutno filtriranih zadetkov iskanja v preglednico Microsoft Excel (.xlsx) z ohranjenim vrstnim redom.
- **Naslovnice v podatkovni bazi:**
  - Shranjevanje naslovnic neposredno v bazo kot MEDIUMBLOB v tabeli cover_images (brez obremenjevanja inode kvot na gostovanju).
  - Samodejna optimizacija slik: preverjanje veljavnosti (Pillow), popravek orientacije (EXIF), zmanjšanje na največ 1200×1700 točk in stiskanje v sodoben format WebP (JPEG kot alternativa).
- **Množični uvoz naslovnic:**
  - Nalaganje do 50 slik hkrati preko zavihka Nastavitve.
  - Samodejno enolično ujemanje po inventarni številki (K-000123.jpg) ali unikatnem ISBN.
  - Zaščita pred dvoumnostjo (če več slik kaže na isto knjigo ali ISBN pripada več fizičnim izvodom).
- **Zunanji katalogi in bibliografski viri:**
  - Samodejno pridobivanje podatkov o knjigi in naslovnice preko ISBN, naslova ali avtorja (COBISS+, Google Books, Open Library, EMKA.si).
  - Neposredne povezave do COBISS+ za ročno bibliografsko preverjanje.
- **Varnostne kopije in obnova:**
  - Celovit izvoz baze podatkov v stisnjenem arhivu ZIP (vključno z manifest.json in database.json) ali JSON.GZ.
  - Varna obnova baze znotraj transakcije z začasnim izklopom preverjanja tujih ključev.
- **Skripte za vzdrževanje:**
  - scripts/create_admin.py: Varno ustvarjanje prvega administratorja in inicializacija sheme.
  - scripts/check_database.py: Preverjanje povezave in štetje zapisov.
  - scripts/verify_project.py: Diagnostika datotečne strukture in uvoženih knjižnic.
  - scripts/diagnose_mariadb_encoding.py: Preverjanje kodiranja tabel in povezave.

### Popravljeno (Fixed)
- **Kodiranje znakov in šumniki (UTF-8):**
  - Rešena težava s slovenskimi šumniki (č, š, ž) na MariaDB strežnikih z vsiljeno nastavitvijo charset=utf8mb4 na ravni povezave in konfiguracije.
  - Varno branje datoteke .env v kodiranju UTF-8 z ignoriranjem ASCII omejitev nekaterih Passenger okolij.
- **Uvoz iz Excela (v2):**
  - Implementirani izolirani transakcijski savepointi (egin_nested()) za vsako vrstico posebej – napaka v posamezni vrstici ne prekine celotnega uvoza.
  - Samodejna korekcija zamaknjenih stolpcev (npr. vrstici 44 in 48 v predlogi, kjer je bil podnaslov združen z avtorjem).
  - Namenski dnevnik uvoza v 	mp/import_xlsx.log.
- **Kaskadno brisanje knjig:**
  - Popravljeno brisanje fizičnega izvoda knjige: eksplicitno brisanje vseh odvisnih zapisov (loans, eading_records, ook_authors, ook_isbns, cover_images) v enotni transakciji, brez vpliva na člane družine ali druge knjige.
- **Odzivna postavitev (Responsive Design):**
  - Popravljena orodna vrstica kataloga (style.css in ase.html z verzijo predpomnilnika), ki ohranja gumbe poravnane na širokih zaslonih in se elegantno prelomi na mobilnih napravah.

---

## [0.5.0] – 2026-11-11
- Podpora za Open Library Covers API z obravnavo preusmeritev na rchive.org.
- Urejanje datuma izposoje in roka vrnitve z logičnim preverjanjem veljavnosti.
- Varno zapiranje SQLite povezav pred stiskanjem varnostne kopije na sistemu Windows.
- Možnost samostojnega prenosa surove .db datoteke.

## [0.4.0] – 2026-11-11
- Večstopenjski prenos mednarodnih naslovnic (Google Books Dynamic Links, Pillow validacija).
- Privzeti 30-dnevni rok vrnitve izposojenih knjig.
- Ločeni obrazci za upravljanje sob, omar in polic v Nastavitvah.
- Preverjanje podvojenih ISBN ob vnosu novega izvoda.
- Dodan zavihek »Izposojene knjige« z možnostjo hitrega označevanja vrnitve.

## [0.1.0 – 0.3.0] – 2026-11-10
- Začetna zasnova projekta in prenos funkcionalnosti iz namizne aplikacije PyQt6 v spletni vmesnik.
- Osnovna shema SQLite, vnos knjig, družinski bralni dnevnik in seznam želja.