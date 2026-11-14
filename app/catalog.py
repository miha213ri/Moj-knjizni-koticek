"""External catalogue lookup and local book-cover handling."""
from io import BytesIO
from urllib.parse import urlparse, quote_plus, parse_qs, urlencode, urlunparse
from html.parser import HTMLParser
import html
import json
import re

import httpx
from PIL import Image, ImageOps

from app.models import CoverImage

MAX_COVER_BYTES = 8 * 1024 * 1024
ALLOWED_COVER_HOSTS = (
    "covers.openlibrary.org", "books.google.com", "books.googleusercontent.com",
    "emka.si", "www.emka.si", "cdn.shopify.com", "archive.org",
)
OPENLIBRARY_PAGE_HOSTS = {"openlibrary.org", "www.openlibrary.org"}

def clean_isbn(value: str) -> str:
    return re.sub(r"[^0-9Xx]", "", value or "").upper()

def is_isbn(value: str) -> bool:
    cleaned = clean_isbn(value)
    return len(cleaned) in (10, 13) and cleaned[:-1].isdigit() and (cleaned[-1].isdigit() or cleaned[-1] == "X")


def _google_result(item):
    info = item.get("volumeInfo", {})
    ids = info.get("industryIdentifiers", [])
    image_links = info.get("imageLinks", {})
    # Google Books exposes several sizes; international editions often have a
    # medium/large image even when thumbnail is absent or points to a tiny stub.
    cover = next((image_links.get(size) for size in (
        "extraLarge", "large", "medium", "small", "thumbnail", "smallThumbnail"
    ) if image_links.get(size)), "")
    has_actual_image_link = bool(cover)
    volume_id = str(item.get("id") or "").strip()
    if not cover and volume_id:
        # The documented imageLinks field is not populated for every volume,
        # although Google may still serve the cover through /books/content.
        cover = f"https://books.google.com/books/content?id={quote_plus(volume_id)}&printsec=frontcover&img=1&zoom=2&source=gbs_api"
    if cover.startswith("http://"):
        cover = "https://" + cover[7:]
    return {
        "source": "Google Books",
        "title": info.get("title", ""),
        "subtitle": info.get("subtitle", ""),
        "authors": ", ".join(info.get("authors", [])),
        "year": str(info.get("publishedDate", ""))[:4],
        "publisher": info.get("publisher", ""),
        "language": info.get("language", ""),
        "isbns": ", ".join(x.get("identifier", "") for x in ids),
        "cover": cover,
        "cover_is_fallback": not has_actual_image_link,
        "description": info.get("description", ""),
    }


def _openlibrary_result(item):
    cover_id = item.get("cover_i")
    isbn_values = item.get("isbn", []) or []
    isbn_cover = next((clean_isbn(value) for value in isbn_values if is_isbn(value)), "")
    cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else (
        f"https://covers.openlibrary.org/b/isbn/{isbn_cover}-L.jpg?default=false" if isbn_cover else ""
    )
    return {
        "source": "Open Library",
        "title": item.get("title", ""),
        "subtitle": "",
        "authors": ", ".join(item.get("author_name", [])[:5]),
        "year": str(item.get("first_publish_year", "")),
        "publisher": ", ".join(item.get("publisher", [])[:2]),
        "language": ", ".join(item.get("language", [])[:3]),
        "isbns": ", ".join(item.get("isbn", [])[:8]),
        "cover": cover_url,
        "description": "",
    }


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        value = " ".join((data or "").split())
        if value:
            self.parts.append(value)

    @property
    def text(self):
        return " ".join(self.parts)


class _ProductLinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.handles = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href", "")
        match = re.search(r"/products/([a-zA-Z0-9-]+)", href)
        if match and match.group(1) not in self.handles:
            self.handles.append(match.group(1))


def _plain_html(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value or "")
    return parser.text


def _emka_metadata(product: dict, query: str) -> dict:
    title = str(product.get("title") or "").strip()
    description = _plain_html(str(product.get("description") or product.get("body") or ""))
    metadata_text = str(product.get("metadata_text") or "")
    tags = product.get("tags") or []
    if isinstance(tags, str):
        tags = [part.strip() for part in tags.split(",")]
    searchable = " ".join([metadata_text, description, " ".join(str(tag) for tag in tags)])

    labels = (
        r"ISBN|Mladinska\s+knjiga\s+ID|Leto\s+izida|Datum\s+izida|Število\s+strani|"
        r"Velikost(?:\s*\([^)]*\))?|Status\s+dobavljivosti|Jezik|Teža|Zbirka(?:\s+MKZ)?|"
        r"Založnik|Zaloznik|Avtor(?:ica)?|Author|Prevajalec|Urednik"
    )

    def field_value(label_pattern: str, source: str = metadata_text, limit: int = 180) -> str:
        if not source:
            return ""
        match = re.search(
            rf"(?:{label_pattern})\s*:?[\s]+(.{{1,{limit}}}?)(?=\s+(?:{labels})\b|$)",
            source,
            re.I,
        )
        return match.group(1).strip(" .:-") if match else ""

    isbn = clean_isbn(field_value(r"ISBN", limit=25))
    if not isbn:
        isbn_match = re.search(r"(?:ISBN(?:-1[03])?\s*[:.]?\s*)([0-9Xx -]{10,20})", searchable, re.I)
        isbn = clean_isbn(isbn_match.group(1)) if isbn_match else ""
    if is_isbn(query) and isbn and isbn != clean_isbn(query):
        return {}
    if is_isbn(query) and not isbn:
        # Never return an ISBN-search result unless the product page confirms the
        # exact identifier; otherwise a title-search hit could be misleading.
        return {}

    author = field_value(r"Avtor(?:ica)?|Author", limit=100)
    publisher = field_value(r"Založnik|Zaloznik", limit=120)
    collection = field_value(r"Zbirka(?:\s+MKZ)?", limit=100)
    year_match = re.search(r"(?:Leto(?:\s+izida)?|Datum\s+izida)\s*:?[\s]*(20\d{2}|19\d{2})", metadata_text or searchable, re.I)
    cover = product.get("featured_image") or product.get("image") or ""
    if isinstance(cover, dict):
        cover = cover.get("url") or cover.get("src") or ""
    if not cover and product.get("images"):
        images = product.get("images")
        cover = images[0].get("src", "") if isinstance(images[0], dict) else images[0]
    if isinstance(cover, str) and cover.startswith("//"):
        cover = "https:" + cover
    handle = product.get("handle") or ""
    product_url = product.get("url") or (f"https://emka.si/products/{handle}" if handle else "")
    if product_url.startswith("/"):
        product_url = "https://emka.si" + product_url
    if not title:
        return {}

    # Avoid importing the entire store navigation and recommendation cards as a book summary.
    if description and len(description) > 5000:
        description = description[:5000].rsplit(" ", 1)[0]
    return {
        "source": "EMKA.si",
        "title": title,
        "subtitle": "",
        "authors": author,
        "year": year_match.group(1) if year_match else "",
        "publisher": publisher or str(product.get("vendor") or ""),
        "language": "sl" if re.search(r"\b(?:SLO|slovenski|slovenska)\b", searchable, re.I) else "",
        "isbns": isbn,
        "cover": str(cover or ""),
        "description": description,
        "url": product_url,
        "collection": collection,
    }


async def _emka_search(client: httpx.AsyncClient, query: str) -> list[dict]:
    """Try EMKA's public Shopify product-search JSON, then product pages by handle.

    This is a best-effort personal lookup provider, not a bulk scraper. If the
    store changes its public search endpoint, the rest of the provider chain remains
    functional and the lookup page still offers a direct EMKA search link.
    """
    products = []
    handles = []
    try:
        response = await client.get(
            "https://emka.si/search/suggest.json",
            params={
                "q": query,
                "resources[type]": "product",
                "resources[limit]": 8,
                "resources[options][unavailable_products]": "show",
            },
        )
        if response.status_code == 200:
            payload = response.json()
            products = payload.get("resources", {}).get("results", {}).get("products", [])
            for product in products:
                handle = product.get("handle") or ""
                if not handle:
                    match = re.search(r"/products/([a-zA-Z0-9-]+)", str(product.get("url") or ""))
                    handle = match.group(1) if match else ""
                if handle and handle not in handles:
                    handles.append(handle)
    except (httpx.HTTPError, ValueError, AttributeError):
        pass

    if not handles:
        try:
            response = await client.get(
                "https://emka.si/search",
                params={"q": query, "type": "product"},
            )
            if response.status_code == 200:
                parser = _ProductLinkExtractor()
                parser.feed(response.text)
                handles.extend(parser.handles[:8])
        except httpx.HTTPError:
            pass

    results = []
    products_by_handle = {}
    for item in products:
        handle = item.get("handle") or ""
        if not handle:
            match = re.search(r"/products/([a-zA-Z0-9-]+)", str(item.get("url") or ""))
            handle = match.group(1) if match else ""
        if handle:
            products_by_handle[handle] = item

    for handle in handles[:8]:
        try:
            response = await client.get(f"https://emka.si/products/{handle}.js")
            if response.status_code != 200:
                product = dict(products_by_handle.get(handle, {}))
                if not product:
                    continue
            else:
                product = response.json()
                # Suggest results contain the public listing URL and sometimes the
                # only available image; retain these fields when .js omits them.
                for key, value in products_by_handle.get(handle, {}).items():
                    if not product.get(key):
                        product[key] = value
            product.setdefault("handle", handle)

            # Read the product page for the exact labelled Slovenian catalogue data.
            try:
                page = await client.get(f"https://emka.si/products/{handle}")
                if page.status_code == 200:
                    page_text = _plain_html(page.text)
                    details_start = re.search(r"Podrobnosti o izdelku", page_text, re.I)
                    if details_start:
                        details_text = page_text[details_start.end():]
                        details_end = re.search(r"Opis", details_text, re.I)
                        if details_end:
                            details_text = details_text[:details_end.start()]
                        product["metadata_text"] = details_text
                        description_start = re.search(r"Opis", page_text, re.I)
                        if description_start and not product.get("description"):
                            product["description"] = page_text[description_start.end():description_start.end() + 3000]
                    if not product.get("featured_image"):
                        image_match = re.search(r"(?:src|data-src)=['\"]([^'\"]*(?:cdn/shop/files|cdn/shop/products)[^'\"]+\.(?:jpg|jpeg|png|webp)[^'\"]*)", page.text, re.I)
                        if image_match:
                            image_url = html.unescape(image_match.group(1))
                            product["featured_image"] = image_url if image_url.startswith("http") else "https://emka.si" + image_url
            except httpx.HTTPError:
                pass
            item = _emka_metadata(product, query)
            if item:
                results.append(item)
        except (httpx.HTTPError, ValueError, TypeError):
            continue

    # If the product suggestion did not expose a handle, retain its basic metadata.
    for handle, product in products_by_handle.items():
        if handle not in handles[:8]:
            item = _emka_metadata(product, query)
            if item:
                results.append(item)
    return results


async def _google_dynamic_cover(client: httpx.AsyncClient, isbn: str) -> str:
    """Use Google's ISBN Dynamic Links endpoint as a cover fallback.

    The endpoint returns thumbnail_url even for volumes whose regular Books API
    record omits imageLinks. It supports ISBN-10 and ISBN-13 identifiers.
    """
    try:
        response = await client.get(
            "https://books.google.com/books",
            params={
                "jscmd": "viewapi",
                "bibkeys": f"ISBN:{isbn}",
                "callback": "processGBSCover",
            },
        )
        if response.status_code != 200:
            return ""
        body = response.text.strip()
        payload_text = body
        if "(" in body and body.endswith(")") or body.endswith(");"):
            start = body.find("(")
            end = body.rfind(")")
            if start >= 0 and end > start:
                payload_text = body[start + 1:end]
        payload = json.loads(payload_text)
        for key, value in payload.items():
            if not isinstance(value, dict):
                continue
            returned_isbn = clean_isbn(key + " " + str(value.get("bib_key") or ""))
            if isbn in returned_isbn:
                return str(value.get("thumbnail_url") or "")
    except (httpx.HTTPError, ValueError, TypeError):
        return ""
    return ""


async def lookup_book(query: str):
    """Search Google Books, Open Library and EMKA; retain source links per result."""
    query = (query or "").strip()
    if not query:
        return []

    results = []
    isbn = clean_isbn(query)
    isbn_mode = is_isbn(query)
    headers = {"User-Agent": "MojKnjizniKoticek/0.5 (personal home library)"}

    async with httpx.AsyncClient(timeout=14, follow_redirects=True, headers=headers) as client:
        google_queries = [f"isbn:{isbn}", isbn] if isbn_mode else [query]
        for google_query in google_queries:
            try:
                response = await client.get(
                    "https://www.googleapis.com/books/v1/volumes",
                    params={"q": google_query, "maxResults": 12, "printType": "books"},
                )
                response.raise_for_status()
                items = response.json().get("items", [])
                results.extend(_google_result(item) for item in items)
                if items:
                    break
            except (httpx.HTTPError, ValueError):
                continue

        if isbn_mode:
            try:
                response = await client.get(f"https://openlibrary.org/isbn/{isbn}.json")
                if response.status_code == 200:
                    edition = response.json()
                    cover_ids = edition.get("covers", [])
                    publishers = edition.get("publishers", [])
                    identifiers = edition.get("isbn_13", []) + edition.get("isbn_10", [])
                    results.append({
                        "source": "Open Library ISBN",
                        "title": edition.get("title", ""),
                        "subtitle": edition.get("subtitle", "") if isinstance(edition.get("subtitle"), str) else ", ".join(edition.get("subtitle", [])),
                        "authors": "",
                        "year": str(edition.get("publish_date", ""))[-4:],
                        "publisher": ", ".join(x if isinstance(x, str) else x.get("name", "") for x in publishers),
                        "language": ", ".join(x.get("key", "").split("/")[-1] for x in edition.get("languages", [])),
                        "isbns": ", ".join(identifiers),
                        "cover": f"https://covers.openlibrary.org/b/id/{cover_ids[0]}-L.jpg" if cover_ids else "",
                        "description": "",
                        "url": f"https://openlibrary.org/isbn/{isbn}",
                    })
            except (httpx.HTTPError, ValueError):
                pass

        try:
            ol_query = f"isbn:{isbn}" if isbn_mode else query
            response = await client.get(
                "https://openlibrary.org/search.json",
                params={"q": ol_query, "limit": 10, "fields": "title,author_name,first_publish_year,publisher,language,isbn,cover_i"},
            )
            response.raise_for_status()
            results.extend(_openlibrary_result(item) for item in response.json().get("docs", []))
        except (httpx.HTTPError, ValueError):
            pass

        # Official Google Dynamic Links can expose thumbnail_url for ISBNs whose
        # regular volumes response omits imageLinks. Merge it into matching records.
        if isbn_mode:
            dynamic_cover = await _google_dynamic_cover(client, isbn)
            if dynamic_cover:
                for result in results:
                    needs_google_cover = result.get("source") == "Google Books" and result.get("cover_is_fallback")
                    if isbn in clean_isbn(result.get("isbns", "")) and (not result.get("cover") or needs_google_cover):
                        result["cover"] = dynamic_cover
                        result["cover_is_fallback"] = False

        # EMKA is especially useful for Slovenian-language editions and recent
        # Mladinska knjiga titles that are missing from international catalogues.
        try:
            results.extend(await _emka_search(client, query))
        except Exception:
            pass

    unique = []
    seen = set()
    for item in results:
        item.setdefault("url", "")
        item.setdefault("collection", "")
        key = (item.get("title", "").casefold(), item.get("authors", "").casefold(), clean_isbn(item.get("isbns", "")))
        if item.get("title") and key not in seen:
            seen.add(key)
            unique.append(item)
    if isbn_mode:
        # ISBN mode should not show a book merely because a provider returned a
        # vaguely related search hit. Only retain records that include the exact ID.
        unique = [item for item in unique if isbn in clean_isbn(item.get("isbns", ""))]
    return unique[:24]


def _store_image(data: bytes, book_id: int, db, source_url: str | None = None) -> str | None:
    """Validate, optimise and persist a cover directly in MariaDB/SQLite."""
    if not data or len(data) > MAX_COVER_BYTES:
        return None
    try:
        with Image.open(BytesIO(data)) as source:
            source.verify()
        with Image.open(BytesIO(data)) as source:
            if source.width < 32 or source.height < 48:
                return None
            image = ImageOps.exif_transpose(source)
            image.thumbnail((1200, 1700), Image.Resampling.LANCZOS)
            if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            output = BytesIO()
            try:
                image.save(output, "WEBP", quality=82, method=5)
                payload, mime = output.getvalue(), "image/webp"
            except Exception:
                output = BytesIO()
                image.save(output, "JPEG", quality=84, optimize=True)
                payload, mime = output.getvalue(), "image/jpeg"
            if len(payload) > 2_000_000:
                output = BytesIO()
                image.thumbnail((900, 1300), Image.Resampling.LANCZOS)
                image.save(output, "JPEG", quality=78, optimize=True)
                payload, mime = output.getvalue(), "image/jpeg"
            cover = db.get(CoverImage, book_id)
            if cover is None:
                cover = CoverImage(book_id=book_id)
                db.add(cover)
            cover.image_data = payload
            cover.mime_type = mime
            cover.width = image.width
            cover.height = image.height
            cover.file_size = len(payload)
            cover.source_url = (source_url or "")[:1000] or None
            return f"/covers/{book_id}"
    except Exception:
        return None


def save_uploaded_cover(data: bytes, book_id: int, db) -> str | None:
    return _store_image(data, book_id, db, "upload")


def _allowed_cover_host(host: str) -> bool:
    host = (host or "").lower().rstrip(".")
    return any(host == item or host.endswith("." + item) for item in ALLOWED_COVER_HOSTS)


def _openlibrary_edition_id(url: str) -> str | None:
    """Return an edition OLID only for a genuine Open Library book page URL."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or (parsed.hostname or "").lower() not in OPENLIBRARY_PAGE_HOSTS:
        return None
    match = re.match(r"^/books/(OL\d+M)(?:\.json)?(?:/.*)?$", parsed.path, re.I)
    return match.group(1).upper() if match else None


async def _openlibrary_edition_cover_urls(client: httpx.AsyncClient, page_url: str) -> list[str]:
    """Resolve an Open Library edition page to its real cover IDs.

    Open Library edition pages are metadata pages, not image URLs. The edition
    JSON contains a `covers` array; Covers API requests then redirect to the
    Internet Archive image host. A direct OLID Covers API URL is kept as fallback.
    """
    olid = _openlibrary_edition_id(page_url)
    if not olid:
        return []
    urls = []
    try:
        response = await client.get(f"https://openlibrary.org/books/{olid}.json")
        if response.status_code == 200:
            payload = response.json()
            cover_ids = payload.get("covers", [])
            if isinstance(cover_ids, list):
                for cover_id in cover_ids:
                    try:
                        numeric_id = int(cover_id)
                    except (TypeError, ValueError):
                        continue
                    if numeric_id > 0:
                        urls.append(
                            f"https://covers.openlibrary.org/b/id/{numeric_id}-L.jpg?default=false"
                        )
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    # Some editions have an OLID-addressable cover even when the JSON covers
    # field is absent or temporarily unavailable.
    urls.append(f"https://covers.openlibrary.org/b/olid/{olid}-L.jpg?default=false")
    return list(dict.fromkeys(urls))


def _cover_candidates(url: str) -> list[str]:
    """Return safe alternate URLs for provider cover endpoints."""
    candidates = []
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not _allowed_cover_host(parsed.hostname or ""):
        return candidates
    candidates.append(url)
    # Google Books imageLinks sometimes point to the HTML-style /books endpoint.
    # Its /books/content endpoint is the more reliable direct image endpoint.
    if (parsed.hostname or "").lower() == "books.google.com" and parsed.path.rstrip("/") == "/books":
        params = parse_qs(parsed.query, keep_blank_values=True)
        volume_id = (params.get("id") or [""])[0]
        if volume_id:
            alternate_params = {
                "id": volume_id,
                "printsec": "frontcover",
                "img": "1",
                "zoom": "2",
                "source": "gbs_api",
            }
            candidates.append(urlunparse(("https", "books.google.com", "/books/content", "", urlencode(alternate_params), "")))
    # Try both HTTP and HTTPS only for provider-listed image hosts. Some older
    # catalogue responses still publish http URLs; redirects are checked below.
    if parsed.scheme == "http":
        candidates.append(urlunparse(("https", parsed.netloc, parsed.path, parsed.params, parsed.query, "")))
    unique = []
    seen = set()
    for item in candidates:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


async def save_cover(url: str, book_id: int, db):
    """Download a provider image safely and store a validated local JPEG.

    Accepts direct image URLs from approved catalogues and Open Library edition
    page URLs such as https://openlibrary.org/books/OL10459823M/.... The latter
    are resolved through the documented edition JSON and Covers API.
    """
    if not url:
        return None
    clean_url = url.strip()
    headers = {
        "User-Agent": "MojKnjizniKoticek/1.0 (family library; cover download)",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": "https://openlibrary.org/",
    }
    async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers=headers) as client:
        # A book page URL is not itself an image. Resolve it to a real cover ID.
        if _openlibrary_edition_id(clean_url):
            candidates = await _openlibrary_edition_cover_urls(client, clean_url)
        else:
            candidates = _cover_candidates(clean_url)
        for candidate in candidates:
            try:
                host = (urlparse(candidate).hostname or "").lower()
                request_headers = dict(headers)
                if host == "covers.openlibrary.org":
                    request_headers["Referer"] = "https://openlibrary.org/"
                elif host == "emka.si" or host.endswith(".emka.si") or host == "cdn.shopify.com":
                    request_headers["Referer"] = "https://emka.si/"
                elif host == "books.google.com":
                    request_headers["Referer"] = "https://books.google.com/"
                response = await client.get(candidate, headers=request_headers)
                final_host = (urlparse(str(response.url)).hostname or "").lower()
                if response.status_code != 200 or not _allowed_cover_host(final_host):
                    continue
                if len(response.content) > MAX_COVER_BYTES:
                    continue
                stored = _store_image(response.content, book_id, db, str(response.url))
                if stored:
                    return stored
            except (httpx.HTTPError, ValueError):
                continue
    return None


