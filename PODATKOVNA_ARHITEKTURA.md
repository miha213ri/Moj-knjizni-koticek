# 🏛️ Podatkovna arhitektura – Moj knjižni kotiček (v1.0.5)

Ta dokument podrobno opisuje podatkovno zasnovo, shemo relacijske baze, varnostne mehanizme, revizijsko sledenje in postopke migracij.

---

## 1. Arhitekturna zasnova in združljivost

Aplikacija uporablja [SQLAlchemy 2.0](https://www.sqlalchemy.org/) ORM in podpira dva podatkovna pogona:
1. **MariaDB / MySQL 8.0+** (produkcijsko okolje na NeoServ / cPanel gostovanju):
   - Privzeto kodiranje: `utf8mb4` s primerjavo `utf8mb4_unicode_ci` (zagotavlja popolno podporo za šumnike in emojije).
   - Gonilnik: PyMySQL s prisilno nastavitvijo `connect_args={"charset": "utf8mb4"}`.
   - Povezovalni bazen (*Connection Pool*): `pool_size=2`, `max_overflow=1`, `pool_recycle=1200`, `pool_pre_ping=True` (prilagojeno za omejitve deljenega gostovanja).
2. **SQLite 3** (lokalni razvoj in avtomatizirani testi):
   - Delovanje v načinu brez potrebe po zunanjem podatkovnem strežniku.
   - `connect_args={"check_same_thread": False}`.

---

## 2. Podatkovni modeli in tabele

### A. Lokacije, uporabniki in pravice (Identity, RBAC & Multi-tenancy)

| Tabela | Opis | Ključna polja |
| :--- | :--- | :--- |
| `locations` | Fizične knjižnice (npr. Domača knjižnica, Vikend, Pisarna). | `id`, `name`, `address`, `active`, `created_at` |
| `users` | Uporabniški računi s 4-stopenjskim RBAC sistemom. | `id`, `username`, `display_name`, `email`, `password_hash`, `role`, `active`, `session_version`, `failed_logins`, `locked_until`, `last_login_at`, `created_at`, `updated_at` |
| `user_locations` | Dodelitev dostopa uporabnikov do posameznih knjižnic. | `user_id` (FK), `location_id` (FK) |
| `family_members` | Družinski profili za bralni dnevnik in sezname želja. | `id`, `user_id` (FK, opcijsko), `name`, `active` |
| `password_resets` | Varni časovno omejeni žetoni za ponastavitev gesla prek e-pošte. | `id`, `user_id` (FK), `token`, `expires_at`, `used`, `created_at` |
| `app_settings` | Dinamične sistemske nastavitve ključ-vrednost. | `key` (PK), `value`, `updated_at` |
| `audit_log` | Celovita revizijska sled varnostnih in skrbniških dogodkov. | `id`, `user_id` (FK), `action`, `details`, `ip_address`, `created_at` |

#### Vloge uporabnikov (RBAC):
- **`ADMIN`**: Popoln dostop do vseh lokacij, uporabniških računov, nastavitev, uvoza/izvoza in varnostnih kopij.
- **`EDITOR`**: Polne pravice urejanja knjižničnega gradiva (dodajanje, urejanje, brisanje knjig, vodenje izposoj) v dodeljenih lokacijah; nima dostopa do administracije sistema.
- **`USER`**: Redni uporabnik: pregled kataloga, dodajanje na lasten seznam želja, lastni bralni dnevnik.
- **`GUEST`**: Samo branje (Read-Only): lahko brska po katalogu, nima pa pravic dodajanja, spreminjanja ali izposojanja (strežniški odziv 403 Forbidden).

---

### B. Knjižnični katalog (Catalog & Physical Inventory)

Vsak zapis v tabeli `books` predstavlja **en fizični izvod knjige**. Več fizičnih izvodov lahko deli isti ISBN ali naslov.

| Tabela | Opis | Ključna polja |
| :--- | :--- | :--- |
| `books` | Fizični izvod knjige z bibliografskimi podatki in lokacijo. | `id`, `location_id` (FK), `inventory_no` (K-XXXXXX), `title`, `subtitle`, `year`, `publisher`, `publication_place`, `genre_id` (FK), `collection_id` (FK), `room_id` (FK), `cabinet_id` (FK), `shelf_id` (FK), `condition`, `status`, `summary`, `notes` |
| `authors` | Šifrant avtorjev knjig. | `id`, `name` |
| `book_authors` | Več-proti-več povezava med knjigo in avtorji z ohranjanjem vrstnega reda. | `book_id` (FK, CASCADE), `author_id` (FK, CASCADE), `position` |
| `book_isbns` | Zapisane ISBN številke za posamezen izvod. | `id`, `book_id` (FK, CASCADE), `isbn` |
| `genres` | Literarni žanri (npr. Leposlovje, Kriminalka, Poezija). | `id`, `name` |
| `collections` | Knjižne zbirke / serije. | `id`, `name` |
| `rooms` | Sobe / prostori znotraj določene lokacije. | `id`, `location_id` (FK), `name` |
| `cabinets` | Omare znotraj posamezne sobe. | `id`, `room_id` (FK), `name` |
| `shelves` | Police znotraj posamezne omare. | `id`, `cabinet_id` (FK), `name` |
| `cover_images` | Naslovnice knjig, shranjene neposredno v bazi. | `book_id` (PK, FK, CASCADE), `image_data` (MEDIUMBLOB), `mime_type`, `width`, `height`, `file_size`, `source_url` |

---

### C. Izposoje, Bralni dnevnik in Želje (Circulation & Reading)

| Tabela | Opis | Ključna polja |
| :--- | :--- | :--- |
| `borrowers` | Zunanji izposojevalci (prijatelji, sosedje, sorodniki). | `id`, `location_id` (FK), `first_name`, `last_name`, `contact`, `address`, `note` |
| `loans` | Zgodovina in aktivne izposoje določenega fizičnega izvoda. | `id`, `book_id` (FK, CASCADE), `borrower_id` (FK), `loan_date`, `due_date`, `returned_date`, `note` |
| `reading_records` | Bralni dnevnik družinskega člana (domača knjiga ali zunanji naslov). | `id`, `family_member_id` (FK), `book_id` (FK, opcijsko), `custom_title`, `custom_author`, `start_date`, `finish_date`, `rating`, `notes` |
| `wishlists` | Seznam knjižnih želja posameznega družinskega člana. | `id`, `family_member_id` (FK), `title`, `author`, `isbn`, `priority`, `notes` |

---

## 3. Shranjevanje naslovnic (MEDIUMBLOB)

- **Razlog za shranjevanje v bazi:** Na deljenih gostovanjih (kot je NeoServ) lahko tisoče majhnih slikovnih datotek hitro preseže dovoljeno število inode enot (*inode quota*). Poleg tega shranjevanje v bazi omogoča enostavno izdelavo celovite varnostne kopije z enim samim izvozom baze.
- **Optimizacija pred vpisom:**
  - Knjižnica Pillow preveri veljavnost slike in popravi EXIF rotacijo.
  - Slika se po potrebi pomanjša na največ **1200 × 1700** točk z ohranitvijo razmerja stranic.
  - Slika se pretvori v format **WebP** z visoko kakovostjo in majhnim podatkovnim odtisom (cilj pod 500 KB, absolutna meja 2 MB).
- **Prikaz:** Strežnik slike posreduje preko namenskega vmesnika `/covers/{book_id}` z ustreznim HTTP predpomnilniškim zaglavjem (`Cache-Control`).

---

## 4. Samodejne migracije podatkovne sheme (Auto-migrations)

Modul `app/migrations.py` zagotavlja samodejno, nevsiljivo posodabljanje baze:
- Ob vsakem zagonu aplikacije pregleda obstoječo strukturo tabel.
- Prepozna manjkajoče stolpce (npr. `email`, `role`, `session_version`, `failed_logins`, `locked_until`) in jih doda z ustreznim tipom in privzeto vrednostjo (`ALTER TABLE ... ADD COLUMN ...`).
- Združljivo tako s SQLite kot z MariaDB/MySQL.
- Obstoječi podatki se v celoti ohranijo brez potrebe po ročnem izvajanju SQL skript.

---

## 5. Varnostne kopije in obnova

Modul `app/server_backup.py` skrbi za celovit izvoz in obnovo:
- Prebere celotno vsebino vseh tabel po definiciji modelov SQLAlchemy.
- Binarne BLOB podatke (naslovnice) pretvori v Base64 niz.
- Datume in decimalna števila serializira v strukturirane JSON objekte.
- Izhod je arhiv ZIP z datotekama `manifest.json` in `database.json` ali stisnjen `database.json.gz`.
- Obnova poteka znotraj ene same SQL transakcije: najprej se začasno izklopijo tuji ključi (`FOREIGN_KEY_CHECKS=0` na MariaDB ali `PRAGMA foreign_keys=OFF` na SQLite), podatki se prepišejo, ob morebitni napaki pa se izvede popolna razveljavitev (`ROLLBACK`).
- Popolna vzvratna združljivost: obnova starejših varnostnih kopij samodejno zapolni nove privzete vrednosti za vloge in sejne različice.
