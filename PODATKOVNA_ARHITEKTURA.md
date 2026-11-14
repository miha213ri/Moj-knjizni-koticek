# 🏛️ Podatkovna arhitektura – Moj knjižni kotiček (v1.0)

Ta dokument podrobno opisuje podatkovno zasnovo, shemo relacijske baze ter varnostne in izvedbene odločitve.

---

## 1. Arhitekturna zasnova in združljivost

Aplikacija uporablja [SQLAlchemy 2.0](https://www.sqlalchemy.org/) ORM in podpira dva podatkovna pogona:
1. **MariaDB / MySQL 8.0+** (produkcijsko okolje na NeoServ / cPanel gostovanju):
   - Privzeto kodiranje: utf8mb4 s primerjavo utf8mb4_unicode_ci (zagotavlja popolno podporo za šumnike in emojije).
   - Gonilnik: PyMySQL s prisilno nastavitvijo connect_args={"charset": "utf8mb4"}.
   - Povezovalni bazen (*Connection Pool*): pool_size=2, max_overflow=1, pool_recycle=1200, pool_pre_ping=True (prilagojeno za omejitve deljenega gostovanja).
2. **SQLite 3** (lokalni razvoj in testiranje):
   - Delovanje v načinu brez potrebe po zunanjem podatkovnem strežniku.
   - connect_args={"check_same_thread": False}.

---

## 2. Podatkovni modeli in tabele

### A. Lokacije in uporabniki (Identity & Multi-tenancy)

| Tabela | Opis | Ključna polja |
| :--- | :--- | :--- |
| locations | Fizične knjižnice (npr. Domača knjižnica, Vikend). | id, 
ame, ctive, created_at |
| users | Uporabniški računi za prijavo v spletno aplikacijo. | id, username, display_name, password_hash, ole (ADMIN/USER), ctive |
| user_locations | Dodelitev dostopa uporabnikov do posameznih knjižnic. | user_id (FK), location_id (FK) |
| amily_members | Družinski profili za bralni dnevnik in sezname želja. | id, location_id (FK), user_id (FK, opcijsko), 
ame, ctive |
| udit_log | Tabela za revizijsko sledenje pomembnejših skrbniških dogodkov. | id, user_id, ction, details, created_at |

---

### B. Knjižnični katalog (Catalog & Physical Inventory)

Vsak zapis v tabeli ooks predstavlja **en fizični izvod knjige**. Več fizičnih izvodov lahko deli isti ISBN ali naslov.

| Tabela | Opis | Ključna polja |
| :--- | :--- | :--- |
| ooks | Fizični izvod knjige z bibliografskimi podatki. | id, location_id (FK), inventory_no (K-XXXXXX), 	itle, subtitle, year, pages, publisher, place, condition, status, summary, 
otes |
| uthors | Šifrant avtorjev knjig. | id, 
ame |
| ook_authors | Več-proti-več povezava med knjigo in avtorji z ohranjanjem vrstnega reda. | ook_id (FK, CASCADE), uthor_id (FK, CASCADE), position |
| ook_isbns | Zapisane ISBN številke za posamezen izvod. | id, ook_id (FK, CASCADE), isbn |
| genres | Literarni žanri (npr. Zgodovinski roman, Kriminalka). | id, 
ame |
| collections | Knjižne zbirke / serije. | id, 
ame |
| ooms | Sobe / prostori znotraj določene lokacije. | id, location_id (FK), 
ame |
| cabinets | Omare znotraj posamezne sobe. | id, oom_id (FK), 
ame |
| shelves | Police znotraj posamezne omare. | id, cabinet_id (FK), 
ame |
| cover_images | Naslovnice knjig, shranjene neposredno v bazi. | ook_id (PK, FK, CASCADE), image_data (MEDIUMBLOB), mime_type, width, height, ile_size, source_url |

---

### C. Izposoje, Bralni dnevnik in Želje (Circulation & Reading)

| Tabela | Opis | Ključna polja |
| :--- | :--- | :--- |
| orrowers | Zunanji izposojevalci (prijatelji, sosedje, sorodniki). | id, location_id (FK), 
ame, contact, 
otes |
| loans | Zgodovina in aktivne izposoje določenega fizičnega izvoda. | id, ook_id (FK, CASCADE), orrower_id (FK), loan_date, due_date, eturned_date, 
otes |
| eading_records | Bralni dnevnik družinskega člana. Knjiga je lahko iz domače knjižnice (ook_id) ali poljuben zunanji naslov (custom_title). | id, amily_member_id (FK), ook_id (FK, opcijsko), custom_title, custom_author, start_date, inish_date, ating, 
otes |
| wishlists | Seznam knjižnih želja posameznega družinskega člana. | id, amily_member_id (FK), 	itle, uthor, isbn, priority, 
otes |

---

## 3. Shranjevanje naslovnic (MEDIUMBLOB)

- **Razlog za shranjevanje v bazi:** Na deljenih gostovanjih (kot je NeoServ) lahko tisoče majhnih slikovnih datotek hitro preseže dovoljeno število inode enot (*inode quota*). Poleg tega shranjevanje v bazi omogoča enostavno izdelavo celovite varnostne kopije z enim samim izvozom baze.
- **Optimizacija pred vpisom:**
  - Knjižnica Pillow preveri veljavnost slike in popravi EXIF rotacijo.
  - Slika se po potrebi pomanjša na največ **1200 × 1700** točk z ohranitvijo razmerja stranic.
  - Slika se pretvori v format **WebP** z visoko kakovostjo in majhnim podatkovnim odtisom (cilj pod 500 KB, absolutna meja 2 MB).
- **Prikaz:** Strežnik slike posreduje preko namenskega vmesnika /covers/{book_id} z ustreznim HTTP predpomnilniškim zaglavjem (Cache-Control).

---

## 4. Varnostne kopije in obnova

Modul pp/server_backup.py skrbi za celovit izvoz:
- Prebere celotno vsebino vseh tabel po definiciji modelov SQLAlchemy.
- Binarne BLOB podatke (naslovnice) pretvori v Base64 niz.
- Datume in decimalna števila serializira v strukturirane JSON objekte.
- Izhod je arhiv ZIP z datotekama manifest.json in database.json ali stisnjen database.json.gz.
- Obnova poteka znotraj ene same SQL transakcije: najprej se začasno izklopijo tuji ključi (FOREIGN_KEY_CHECKS=0), podatki se prepišejo, ob morebitni napaki pa se izvede popolna razveljavitev (ROLLBACK).