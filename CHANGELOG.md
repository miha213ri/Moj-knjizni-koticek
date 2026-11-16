# Dnevnik sprememb (Changelog)

Vse pomembne spremembe v projektu **Moj knjižni kotiček** so zabeležene v tej datoteki.

Format temelji na [Keep a Changelog](https://keepachangelog.com/sl/1.0.0/), projekt pa sledi [Semantičnemu verzijskemu označevanju](https://semver.org/).

---

## [1.0.5] – 2026-11-16

### Celovita nadgradnja varnosti, vlog in administracije (Enterprise & Security Release)

Ta izdaja prinaša celovito implementacijo naprednih zalednih (Backend), podatkovnih in varnostnih mehanizmov ter izpopolnitev uporabniške izkušnje skladno s sodobnimi spletnimi in varnostnimi standardi (GDPR, OWASP).

Projekt je bil razvit in izpopolnjen v sodelovanju z umetno inteligenco **ChatGPT** (OpenAI). Celoten potek načrtovanja, diagnostike in iterativnega razvoja je dokumentiran v [deljenem pogovoru ChatGPT](https://chatgpt.com/share/6af8b720-f718-83ed-80ae-dea8a4c323ac).

### Dodano (Added)
- **Štiri ravni uporabniških vlog (RBAC):**
  - `ADMIN`: Popoln nadzor nad sistemom, vsemi lokacijami, uporabniki, nastavitvami, revizijsko sledjo ter varnostnimi kopijami.
  - `EDITOR`: Polne pravice vnosa, urejanja in brisanja knjig ter vodenja izposoj, brez dostopa do sistemske administracije.
  - `USER`: Redni uporabnik z možnostjo pregledovanja kataloga, vodenja lastnega bralnega dnevnika in seznama želja.
  - `GUEST`: Izključno vpogled (read-only) v katalog dodeljenih knjižnic; vsakršno spreminjanje podatkov ali izposoja je strežniško blokirano (HTTP 403).
- **Avtentikacija in življenjski cikel računov:**
  - Samodejna registracija uporabnikov z uveljavljanjem stroge varnostne politike gesel (najmanj 12 znakov ter obvezna vsaj ena številka ali posebni znak).
  - Varno zgoščevanje gesel s funkcijo `scrypt` z naključno soljo.
  - Samodejno pošiljanje prijavnih podatkov (uporabniško ime in začasno geslo) na e-pošto ob ustvarjanju računa ali administratorski ponastavitvi gesla (vključno z namensko kljukico v obrazcih).
  - Pozabljeno geslo z varno ponastavitvijo prek enkratnih, časovno omejenih kriptografskih žetonov (`PasswordReset`).
  - Dinamična konfiguracija SMTP strežnika neposredno v bazi (`app_settings`) s podporo za SSL (vrata 465) in STARTTLS (vrata 587) ter varnostnim zaledjem v `.env`.
  - Vgrajeno orodje za takojšen preizkus SMTP povezave s pošiljanjem testnega sporočila neposredno iz skrbniške nadzorne plošče (`/admin/smtp/test`).
  - Varno beleženje v `tmp/mail.log`, kadar SMTP strežnik še ni konfiguriran ali kadar pošiljanje ni mogoče.
- **Varnostni mehanizmi in seje:**
  - Zaščita pred napadi s surovo silo (Brute-force): samodejno začasno zaklepanje uporabniškega računa po 5 zaporednih neuspelih poskusih prijave (`locked_until`).
  - Možnost takojšnjega skrbniškega odklepa računa prek administratorske plošče.
  - Upravljanje sej in takojšen preklic vseh aktivnih sej na vseh napravah prek inkrementiranja `session_version`.
  - Varnostne HTTP glave: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-XSS-Protection: 1; mode=block`.
  - Podpisani sejni piškotki z zaščitnimi zastavicami `HttpOnly`, `SameSite=Lax` ter izbirnim `Secure` (HTTPS).
  - Rate limiting prijav po IP naslovu.
- **Uporabniški profil in nastavitve:**
  - Nova stran `/profile` za pregled in urejanje osebnih podatkov (prikazno ime, e-pošta), spremembo gesla ter gumb za odjavo vseh ostalih naprav.
  - Centralne nastavitve aplikacije (`app_settings`): vklop/izklop javne registracije, privzeti rok izposoj.
- **Revizijska sled in nadzorna plošča:**
  - Beleženje pomembnih varnostnih in skrbniških dogodkov v tabelo `audit_log` (prijave, zaklepi, odklepi, registracije, menjave gesel, preklici sej).
  - Nadzorna plošča za administratorje s statističnimi karticami (število knjig, aktivnih izposoj, uporabnikov, lokacij), filtri in pregledom zadnjih revizijskih zapisov.
- **Samodejne migracije sheme (Auto-migrations):**
  - Funkcija `auto_migrate_schema(engine)` ob zagonu aplikacije preveri obstoječe tabele ter samodejno doda manjkajoče stolpce in nove tabele brez izgube obstoječih podatkov na SQLite in MariaDB.
- **Zasebnost in GDPR:**
  - Uradna izjava o piškotkih: aplikacija ne uporablja nobenih analitičnih, sledilnih ali oglaševalskih piškotkov, temveč izključno tehnično nujne sejne piškotke.
  - Vzpostavljena datoteka `/robots.txt` z direktivo `Disallow: /` ter oznakami `noindex, nofollow` za zaščito zasebnosti zasebne knjižnice pred spletnimi iskalniki.
- **Avtomatizirano testiranje:**
  - Popolna zbirka testov `tests/test_full_suite.py` (9 testnih sklopov), ki celovito preverja varnostne glave, registracijo in moč gesel, zaklepanje računov, ponastavitev gesel, seje, pravice vlog, knjižnične operacije, Excel izvoz, varnostne kopije ter dinamične SMTP nastavitve in pošiljanje prijavnih podatkov.

---

## [1.0.0] – 2026-11-14

### Uradna stabilna izdaja (Production Release)
Ta izdaja predstavlja prelomno preobrazbo aplikacije iz lokalnega namiznega orodja v sodobno večuporabniško spletno aplikacijo, pripravljeno za deljeno gostovanje (LiteSpeed / Passenger WSGI) ter lokalno uporabo.

Projekt je bil razvit in izpopolnjen v tesnem sodelovanju z umetno inteligenco **ChatGPT** (OpenAI). Celoten potek načrtovanja, diagnostike in iterativnega razvoja je dokumentiran v [deljenem pogovoru ChatGPT](https://chatgpt.com/share/6af8b720-f718-83ed-80ae-dea8a4c323ac).

### Dodano (Added)
- **Strežniška arhitektura FastAPI:**
  - Podpora za produkcijsko poganjanje preko LiteSpeed / cPanel z `passenger_wsgi.py` in `a2wsgi` adapterjem.
  - Podpora za lokalni razvoj preko `run.py` (Uvicorn).
- **Podpora za podatkovne baze:**
  - Polna podpora za MariaDB / MySQL s PyMySQL gonilnikom.
  - Samodejni preklop na lokalno SQLite bazo, kadar strežniška baza ni nastavljena.
  - Optimiziran bazni bazen (connection pool pre-ping, recycle) za stabilno delovanje na deljenem gostovanju.
- **Avtentikacija in večuporabniški sistem:**
  - Prijavni sistem z varno šifriranimi gesli (`scrypt`).
  - Podpora za več fizičnih knjižnic/lokacij (npr. domača knjižnica, vikend, pisarna) s skupnim katalogom.
- **Katalog knjig in napredno brskanje:**
  - Preklop med kartičnim (KARTICE) in tabelaričnim (SEZNAM) pogledom.
  - Razvrščanje po vseh ključnih stolpcih (inventarna št., naslov, avtorji, leto, ISBN, žanr, zbirka, lokacija, stanje, status).
  - Izvoz trenutno filtriranih zadetkov iskanja v preglednico Microsoft Excel (.xlsx) z ohranjenim vrstnim redom.
- **Naslovnice v podatkovni bazi:**
  - Shranjevanje naslovnic neposredno v bazo kot `MEDIUMBLOB` v tabeli `cover_images` (brez obremenjevanja inode kvot na gostovanju).
  - Samodejna optimizacija slik: preverjanje veljavnosti (Pillow), popravek orientacije (EXIF), zmanjšanje na največ 1200×1700 točk in stiskanje v format WebP.
- **Množični uvoz naslovnic:**
  - Nalaganje do 50 slik hkrati preko zavihka Nastavitve.
  - Samodejno enolično ujemanje po inventarni številki (`K-000123.jpg`) ali unikatnem ISBN.
  - Zaščita pred dvoumnostjo (če več slik kaže na isto knjigo ali ISBN pripada več fizičnim izvodom).
- **Zunanji katalogi in bibliografski viri:**
  - Samodejno pridobivanje podatkov o knjigi in naslovnice preko ISBN, naslova ali avtorja (COBISS+, Google Books, Open Library, EMKA.si).
  - Neposredne povezave do COBISS+ za ročno bibliografsko preverjanje.
- **Varnostne kopije in obnova:**
  - Celovit izvoz baze podatkov v stisnjenem arhivu ZIP (vključno z `manifest.json` in `database.json`) ali JSON.GZ.
  - Varna obnova baze znotraj transakcije z začasnim izklopom preverjanja tujih ključev.
- **Skripte za vzdrževanje:**
  - `scripts/create_admin.py`: Varno ustvarjanje prvega administratorja in inicializacija sheme.
  - `scripts/check_database.py`: Preverjanje povezave in štetje zapisov.
  - `scripts/verify_project.py`: Diagnostika datotečne strukture in uvoženih knjižnic.
  - `scripts/diagnose_mariadb_encoding.py`: Preverjanje kodiranja tabel in povezave.

### Popravljeno (Fixed)
- **Kodiranje znakov in šumniki (UTF-8):**
  - Rešena težava s slovenskimi šumniki (č, š, ž) na MariaDB strežnikih z vsiljeno nastavitvijo `charset=utf8mb4` na ravni povezave in konfiguracije.
  - Varno branje datoteke `.env` v kodiranju UTF-8 z ignoriranjem ASCII omejitev nekaterih Passenger okolij.
- **Uvoz iz Excela (v2):**
  - Implementirani izolirani transakcijski savepointi (`begin_nested()`) za vsako vrstico posebej – napaka v posamezni vrstici ne prekine celotnega uvoza.
  - Samodejna korekcija zamaknjenih stolpcev (npr. vrstici 44 in 48 v predlogi, kjer je bil podnaslov združen z avtorjem).
  - Namenski dnevnik uvoza v `tmp/import_xlsx.log`.
- **Kaskadno brisanje knjig:**
  - Popravljeno brisanje fizičnega izvoda knjige: eksplicitno brisanje vseh odvisnih zapisov (`loans`, `reading_records`, `book_authors`, `book_isbns`, `cover_images`) v enotni transakciji.
- **Odzivna postavitev (Responsive Design):**
  - Popravljena orodna vrstica kataloga (`style.css`), ki ohranja gumbe poravnane na širokih zaslonih in se elegantno prelomi na mobilnih napravah.

---

## [0.5.0] – 2026-11-11
- Podpora za Open Library Covers API z obravnavo preusmeritev na archive.org.
- Urejanje datuma izposoje in roka vrnitve z logičnim preverjanjem veljavnosti.
- Varno zapiranje SQLite povezav pred stiskanjem varnostne kopije na sistemu Windows.

## [0.4.0] – 2026-11-11
- Večstopenjski prenos mednarodnih naslovnic (Google Books Dynamic Links, Pillow validacija).
- Privzeti 30-dnevni rok vrnitve izposojenih knjig.
- Ločeni obrazci za upravljanje sob, omar in polic v Nastavitvah.
- Preverjanje podvojenih ISBN ob vnosu novega izvoda.

## [0.1.0 – 0.3.0] – 2026-11-10
- Začetna zasnova projekta in prenos funkcionalnosti iz namizne aplikacije PyQt6 v spletni vmesnik.
- Osnovna shema SQLite, vnos knjig, družinski bralni dnevnik in seznam želja.
