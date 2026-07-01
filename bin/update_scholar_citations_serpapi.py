#!/usr/bin/env python3
"""Update publication citation data from Google Scholar, Semantic Scholar, and ADS.

The script rewrites `_data/publications.yml` with a nested `citations` structure
and writes per-source cited-paper caches to `_data/publication_cited_documents.yml`.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

BIB_PATH = Path("_bibliography/papers.bib")
PUBLICATIONS_PATH = Path("_data/publications.yml")
SOCIALS_PATH = Path("_data/socials.yml")
CITED_DOCUMENTS_PATH = Path("_data/publication_cited_documents.yml")

SERPAPI_URL = "https://serpapi.com/search.json"
SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1"
ADS_API_URL = "https://api.adsabs.harvard.edu/v1/search/query"

GOOGLE_AUTHOR_PAGE_SIZE = 100
SERPAPI_CITATION_PAGE_SIZE = 20
SEMANTIC_SCHOLAR_CITATION_PAGE_SIZE = 100
ADS_CITATION_PAGE_SIZE = 2000
HTTP_429_RETRIES = 120
HTTP_429_RETRY_DELAY_SECONDS = 1.0
MAX_SCHOLAR_AUTHOR_ARTICLES = 500


@dataclass(frozen=True)
class BibEntry:
    key: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class BibMetadata:
    title: str | None
    eprint: str | None
    doi: str | None
    url: str | None


@dataclass(frozen=True)
class PublicationBlock:
    key: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class CitationItem:
    title: str
    link: str


def load_env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def fetch_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    request_headers = {"User-Agent": "zjsxply-citation-updater/3.0"}
    if headers:
        request_headers.update(headers)

    transient_retries = 3
    total_attempts = max(HTTP_429_RETRIES + 1, transient_retries + 1)

    for attempt in range(total_attempts):
        request = urllib.request.Request(url, headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 429 and attempt < HTTP_429_RETRIES:
                time.sleep(HTTP_429_RETRY_DELAY_SECONDS)
                continue

            if error.code in {500, 502, 503, 504} and attempt < transient_retries:
                retry_after = error.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                time.sleep(delay)
                continue

            body = error.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"HTTP {error.code} for {url}: {body}") from error
        except urllib.error.URLError as error:
            if attempt < transient_retries:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(f"URL error for {url}: {error}") from error

    raise RuntimeError(f"Failed to fetch {url}")


def fetch_serpapi(params: dict[str, str], api_key: str) -> dict[str, Any]:
    payload = dict(params)
    payload["api_key"] = api_key
    url = f"{SERPAPI_URL}?{urllib.parse.urlencode(payload)}"
    return fetch_json(url)


def fetch_semantic_scholar(
    path: str,
    params: dict[str, str],
    api_key: str | None,
) -> dict[str, Any]:
    url = f"{SEMANTIC_SCHOLAR_API_URL}{path}?{urllib.parse.urlencode(params)}"
    headers = {"x-api-key": api_key} if api_key else None
    return fetch_json(url, headers=headers)


def fetch_ads(params: dict[str, str], token: str) -> dict[str, Any]:
    url = f"{ADS_API_URL}?{urllib.parse.urlencode(params)}"
    headers = {"Authorization": f"Bearer {token}"}
    return fetch_json(url, headers=headers)


def load_scholar_user_id() -> str:
    data = yaml.safe_load(SOCIALS_PATH.read_text(encoding="utf-8")) or {}
    scholar_userid = data.get("scholar_userid")
    if not scholar_userid:
        raise ValueError(f"Could not find scholar_userid in {SOCIALS_PATH}")
    return str(scholar_userid)


def find_bib_entries(text: str) -> list[BibEntry]:
    entries: list[BibEntry] = []
    index = 0
    while True:
        at_index = text.find("@", index)
        if at_index == -1:
            break

        open_index = text.find("{", at_index)
        if open_index == -1:
            break

        key_end = text.find(",", open_index)
        if key_end == -1:
            break
        key = text[open_index + 1 : key_end].strip()

        depth = 0
        position = open_index
        while position < len(text):
            char = text[position]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = position + 1
                    entries.append(BibEntry(key=key, start=at_index, end=end, text=text[at_index:end]))
                    index = end
                    break
            position += 1
        else:
            raise ValueError(f"Unbalanced BibTeX braces near byte offset {at_index}")

    return entries


def find_publication_blocks(text: str) -> list[PublicationBlock]:
    pattern = re.compile(r"(?ms)^([A-Za-z0-9_.:-]+):\n(.*?)(?=^[A-Za-z0-9_.:-]+:\n|\Z)")
    return [
        PublicationBlock(key=match.group(1), start=match.start(), end=match.end(), text=match.group(0))
        for match in pattern.finditer(text)
    ]


def extract_field(entry_text: str, field_name: str) -> str | None:
    pattern = re.compile(rf"(?im)^\s*{re.escape(field_name)}\s*=\s*([{{\"])")
    match = pattern.search(entry_text)
    if not match:
        return None

    opener = match.group(1)
    value_start = match.end()
    if opener == '"':
        value_end = entry_text.find('"', value_start)
        if value_end == -1:
            return None
        return entry_text[value_start:value_end].strip()

    depth = 1
    position = value_start
    while position < len(entry_text):
        char = entry_text[position]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return entry_text[value_start:position].strip()
        position += 1

    return None


def bib_metadata_by_key() -> dict[str, BibMetadata]:
    original = BIB_PATH.read_text(encoding="utf-8")
    metadata: dict[str, BibMetadata] = {}
    for entry in find_bib_entries(original):
        metadata[entry.key] = BibMetadata(
            title=extract_field(entry.text, "title"),
            eprint=extract_field(entry.text, "eprint"),
            doi=extract_field(entry.text, "doi"),
            url=extract_field(entry.text, "url"),
        )
    return metadata


def normalize_title(title: str | None) -> str:
    if not title:
        return ""

    normalized = title
    for old in [r"\emph", r"\textbf", r"\textit", "{", "}"]:
        normalized = normalized.replace(old, " ")
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_arxiv_id(arxiv_id: str) -> str:
    arxiv_id = arxiv_id.strip()
    arxiv_id = re.sub(r"(?i)^arxiv:", "", arxiv_id)
    arxiv_id = re.sub(r"(?i)^https?://arxiv\.org/(?:abs|pdf)/", "", arxiv_id)
    arxiv_id = arxiv_id.removesuffix(".pdf")
    return re.sub(r"v\d+$", "", arxiv_id).lower()


def normalize_doi(doi: str) -> str:
    doi = doi.strip()
    doi = re.sub(r"(?i)^https?://(?:dx\.)?doi\.org/", "", doi)
    return doi.rstrip(".,;:)]}").lower()


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc:
        return None

    path = parsed.path.rstrip("/")
    return urllib.parse.urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", ""))


def article_title(article: dict[str, Any]) -> str | None:
    title = article.get("title")
    if isinstance(title, list) and title:
        title = title[0]
    return title if isinstance(title, str) else None


def citation_item_key(item: CitationItem) -> str:
    title_key = normalize_title(item.title)
    if title_key:
        return f"title:{title_key}"
    link_key = normalize_url(item.link)
    return f"link:{link_key}" if link_key else f"raw:{item.title}|{item.link}"


def unique_items(items: list[CitationItem]) -> list[CitationItem]:
    seen: set[str] = set()
    ordered: list[CitationItem] = []
    for item in items:
        key = citation_item_key(item)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


def item_dict(item: CitationItem) -> dict[str, str]:
    return {"title": item.title, "link": item.link}


def citation_channel(
    *,
    identifier: str | None = None,
    url: str | None,
    citations: int,
    ids: list[str] | None = None,
    extra_non_duplicate: int | None = None,
) -> dict[str, Any]:
    channel: dict[str, Any] = {}
    if identifier is not None:
        channel["id"] = identifier
    if ids is not None:
        channel["ids"] = ids
    if url is not None:
        channel["url"] = url
    channel["citations"] = citations
    if extra_non_duplicate is not None:
        channel["extra_non_duplicate"] = extra_non_duplicate
    return channel


def parse_publication(block: PublicationBlock) -> dict[str, Any]:
    loaded = yaml.safe_load(block.text)
    if not isinstance(loaded, dict):
        return {}
    publication = loaded.get(block.key)
    return publication if isinstance(publication, dict) else {}


def empty_cited_documents_entry() -> dict[str, dict[str, list[dict[str, str]]]]:
    return {
        "google_scholar": {"documents": []},
        "semantic_scholar": {"documents": []},
        "ads": {"documents": []},
    }


def load_existing_cited_documents() -> dict[str, dict[str, Any]]:
    if not CITED_DOCUMENTS_PATH.exists():
        return {}

    loaded = yaml.safe_load(CITED_DOCUMENTS_PATH.read_text(encoding="utf-8")) or {}
    papers = loaded.get("papers")
    return papers if isinstance(papers, dict) else {}


def publication_source_section(publication: dict[str, Any], source: str) -> dict[str, Any]:
    citations = publication.get("citations")
    if isinstance(citations, dict):
        section = citations.get(source)
        if isinstance(section, dict):
            return section

    section = publication.get(source)
    if isinstance(section, dict):
        return section

    return {}


def publication_has_citation_config(publication: dict[str, Any]) -> bool:
    if isinstance(publication.get("citations"), dict):
        return True

    if any(key in publication for key in ("google_scholar", "semantic_scholar", "ads", "total")):
        return True

    return any(
        key in publication
        for key in (
            "scholar_citation_ids",
            "scholar_citations",
            "semantic_scholar_paper_id",
            "semantic_scholar_url",
            "semantic_scholar_citations",
            "combined_citations",
            "ads_id",
            "ads_bibcode",
        )
    )


def as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return [str(value)]


def extract_cites_ids_from_url(url: str | None) -> list[str]:
    if not url:
        return []
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    cites = query.get("cites")
    if not cites:
        return []
    return [part for part in cites[0].split(",") if part]


def normalize_google_ids(publication: dict[str, Any]) -> list[str]:
    google = publication_source_section(publication, "google_scholar")

    ids = google.get("ids")
    if ids:
        return as_string_list(ids)

    ids = google.get("id")
    if ids:
        return as_string_list(ids)

    ids = publication.get("scholar_citation_ids")
    if ids:
        return as_string_list(ids)

    ids_from_url = extract_cites_ids_from_url(google.get("url"))
    if ids_from_url:
        return ids_from_url

    return []


def normalize_semantic_id(publication: dict[str, Any], bib_metadata: BibMetadata | None) -> str | None:
    semantic = publication_source_section(publication, "semantic_scholar")
    if semantic:
        for field_name in ("id", "paper_id", "paperId", "semantic_scholar_paper_id"):
            value = semantic.get(field_name)
            if isinstance(value, str) and value.strip():
                return value.strip()

    for field_name in ("semantic_scholar_paper_id", "semantic_scholar_id"):
        value = publication.get(field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()

    if bib_metadata and bib_metadata.eprint:
        return f"arXiv:{normalize_arxiv_id(bib_metadata.eprint)}"

    doi = publication.get("doi") or (bib_metadata.doi if bib_metadata else None)
    if isinstance(doi, str) and doi.strip():
        return f"DOI:{normalize_doi(doi)}"

    return None


def fetch_google_author_articles(author_id: str, api_key: str) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    start = 0

    while True:
        payload = fetch_serpapi(
            {
                "engine": "google_scholar_author",
                "author_id": author_id,
                "hl": "en",
                "num": str(GOOGLE_AUTHOR_PAGE_SIZE),
                "start": str(start),
            },
            api_key,
        )
        page_articles = payload.get("articles") or []
        for article in page_articles:
            if isinstance(article, dict):
                articles.append(article)

        if len(page_articles) < GOOGLE_AUTHOR_PAGE_SIZE:
            break

        start += GOOGLE_AUTHOR_PAGE_SIZE
        if start >= MAX_SCHOLAR_AUTHOR_ARTICLES:
            break

    return articles


def index_articles_by_title(articles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_title: dict[str, dict[str, Any]] = {}
    for article in articles:
        title = article_title(article)
        if not title:
            continue
        by_title.setdefault(normalize_title(title), article)
    return by_title


def resolve_google_ids(
    publication: dict[str, Any],
    bib_metadata: BibMetadata | None,
    articles_by_title: dict[str, dict[str, Any]] | None,
) -> list[str]:
    ids = normalize_google_ids(publication)
    if ids:
        return ids

    if not articles_by_title or not bib_metadata or not bib_metadata.title:
        return []

    article = articles_by_title.get(normalize_title(bib_metadata.title))
    if not article:
        return []
    cited_by = article.get("cited_by")
    if not isinstance(cited_by, dict):
        return []

    for field_name in ("link", "serpapi_link"):
        link = cited_by.get(field_name)
        if isinstance(link, str):
            ids = extract_cites_ids_from_url(link)
            if ids:
                return ids
    return []


def fetch_serpapi_citing_items(cites_ids: list[str], api_key: str) -> list[CitationItem]:
    if not cites_ids:
        return []

    items: list[CitationItem] = []
    start = 0
    total_results: int | None = None

    while True:
        payload = fetch_serpapi(
            {
                "engine": "google_scholar",
                "cites": ",".join(cites_ids),
                "hl": "en",
                "num": str(SERPAPI_CITATION_PAGE_SIZE),
                "start": str(start),
            },
            api_key,
        )

        if total_results is None:
            search_information = payload.get("search_information")
            if isinstance(search_information, dict):
                raw_total = search_information.get("total_results")
                if isinstance(raw_total, int):
                    total_results = raw_total
                elif isinstance(raw_total, str) and raw_total.isdigit():
                    total_results = int(raw_total)

        page_results = payload.get("organic_results") or []
        for result in page_results:
            if not isinstance(result, dict):
                continue
            title = result.get("title")
            if not isinstance(title, str) or not title.strip():
                continue
            link = result.get("link")
            if not isinstance(link, str) or not link.strip():
                link = result.get("serpapi_link")
            if not isinstance(link, str) or not link.strip():
                continue
            items.append(CitationItem(title=title.strip(), link=link.strip()))

        if not page_results:
            break
        if total_results is not None and len(items) >= total_results:
            break

        start += len(page_results)

    return unique_items(items)


def resolve_semantic_scholar_id(
    publication: dict[str, Any],
    bib_metadata: BibMetadata | None,
) -> str | None:
    return normalize_semantic_id(publication, bib_metadata)


def fetch_semantic_scholar_citing_items(paper_id: str, api_key: str | None) -> list[CitationItem]:
    if not paper_id:
        return []

    items: list[CitationItem] = []
    offset = 0

    while True:
        payload = fetch_semantic_scholar(
            f"/paper/{urllib.parse.quote(paper_id, safe='')}/citations",
            {
                "fields": "citingPaper.paperId,citingPaper.title,citingPaper.url",
                "limit": str(SEMANTIC_SCHOLAR_CITATION_PAGE_SIZE),
                "offset": str(offset),
            },
            api_key,
        )

        page_items = payload.get("data") or []
        for item in page_items:
            if not isinstance(item, dict):
                continue
            citing = item.get("citingPaper")
            if not isinstance(citing, dict):
                continue
            title = citing.get("title")
            if not isinstance(title, str) or not title.strip():
                continue
            link = citing.get("url")
            if not isinstance(link, str) or not link.strip():
                paper_id_value = citing.get("paperId")
                if isinstance(paper_id_value, str) and paper_id_value.strip():
                    link = f"https://www.semanticscholar.org/paper/{paper_id_value.strip()}"
            if not isinstance(link, str) or not link.strip():
                continue
            items.append(CitationItem(title=title.strip(), link=link.strip()))

        next_offset = payload.get("next")
        if next_offset is None:
            break
        offset = int(next_offset)

    return unique_items(items)


def ads_search_bibcode(query: str, token: str | None) -> str | None:
    if not token:
        return None
    payload = fetch_ads({"q": query, "fl": "bibcode", "rows": "1"}, token)
    docs = payload.get("response", {}).get("docs", [])
    if not docs:
        return None
    bibcode = docs[0].get("bibcode")
    return bibcode if isinstance(bibcode, str) else None


def resolve_ads_bibcode(
    publication: dict[str, Any],
    bib_metadata: BibMetadata | None,
    token: str | None,
) -> str | None:
    ads = publication_source_section(publication, "ads")
    if ads:
        for field_name in ("id", "bibcode", "ads_id"):
            value = ads.get(field_name)
            if isinstance(value, str) and value.strip():
                return value.strip()

    for field_name in ("ads_id", "ads_bibcode"):
        value = publication.get(field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()

    if not token:
        return None

    if bib_metadata and bib_metadata.eprint:
        bibcode = ads_search_bibcode(f"identifier:arXiv:{normalize_arxiv_id(bib_metadata.eprint)}", token)
        if bibcode:
            return bibcode

    doi = bib_metadata.doi if bib_metadata else None
    if doi:
        bibcode = ads_search_bibcode(f"doi:{normalize_doi(doi)}", token)
        if bibcode:
            return bibcode

    return None


def fetch_ads_citing_items(bibcode: str, token: str) -> list[CitationItem]:
    if not bibcode:
        return []

    items: list[CitationItem] = []
    start = 0
    total_results: int | None = None

    while True:
        payload = fetch_ads(
            {
                "q": f"citations({bibcode})",
                "fl": "bibcode,title,identifier",
                "rows": str(ADS_CITATION_PAGE_SIZE),
                "start": str(start),
            },
            token,
        )

        response = payload.get("response", {})
        if total_results is None:
            raw_total = response.get("numFound")
            if isinstance(raw_total, int):
                total_results = raw_total
            elif isinstance(raw_total, str) and raw_total.isdigit():
                total_results = int(raw_total)

        docs = response.get("docs") or []
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            title = doc.get("title")
            if isinstance(title, list) and title:
                title = title[0]
            if not isinstance(title, str) or not title.strip():
                continue
            cited_bibcode = doc.get("bibcode")
            if not isinstance(cited_bibcode, str) or not cited_bibcode.strip():
                continue
            items.append(
                CitationItem(
                    title=title.strip(),
                    link=f"https://ui.adsabs.harvard.edu/abs/{cited_bibcode.strip()}/abstract",
                )
            )

        if not docs:
            break
        if total_results is not None and len(items) >= total_results:
            break
        if len(docs) < ADS_CITATION_PAGE_SIZE:
            break

        start += len(docs)

    return unique_items(items)


def citation_item_sort_key(item: CitationItem) -> tuple[str, str, str]:
    return (normalize_title(item.title), item.title.casefold(), normalize_url(item.link) or item.link.casefold())


def citation_item_list(items: list[CitationItem]) -> list[dict[str, str]]:
    return [item_dict(item) for item in sorted(items, key=citation_item_sort_key)]


def generate_publication_citations(
    publication: dict[str, Any],
    bib_metadata: BibMetadata | None,
    articles_by_title: dict[str, dict[str, Any]] | None,
    serpapi_key: str,
    semantic_scholar_key: str | None,
    ads_token: str,
) -> tuple[dict[str, Any], dict[str, list[dict[str, str]]]]:
    google_ids = resolve_google_ids(publication, bib_metadata, articles_by_title)
    google_url = f"https://scholar.google.com/scholar?cites={','.join(google_ids)}" if google_ids else None
    google_items = fetch_serpapi_citing_items(google_ids, serpapi_key) if google_ids else []

    semantic_id = resolve_semantic_scholar_id(publication, bib_metadata)
    semantic_url = None
    semantic = publication_source_section(publication, "semantic_scholar")
    raw_url = semantic.get("url")
    if isinstance(raw_url, str) and raw_url.strip():
        semantic_url = raw_url.strip()
    elif isinstance(publication.get("semantic_scholar_url"), str) and publication["semantic_scholar_url"].strip():
        semantic_url = publication["semantic_scholar_url"].strip()
    elif semantic_id:
        semantic_url = f"https://www.semanticscholar.org/paper/{urllib.parse.quote(semantic_id, safe='')}"
    semantic_items = fetch_semantic_scholar_citing_items(semantic_id, semantic_scholar_key) if semantic_id else []

    ads_bibcode = resolve_ads_bibcode(publication, bib_metadata, ads_token)
    ads = publication_source_section(publication, "ads")
    ads_url = None
    raw_ads_url = ads.get("url")
    if isinstance(raw_ads_url, str) and raw_ads_url.strip():
        ads_url = raw_ads_url.strip()
    elif ads_bibcode:
        ads_url = f"https://ui.adsabs.harvard.edu/abs/{ads_bibcode}/citations"
    ads_items = fetch_ads_citing_items(ads_bibcode, ads_token) if ads_bibcode else []

    google_items = unique_items(google_items)
    semantic_items = unique_items(semantic_items)
    ads_items = unique_items(ads_items)

    google_key_set = {citation_item_key(item) for item in google_items}
    semantic_key_set = {citation_item_key(item) for item in semantic_items}
    ads_key_set = {citation_item_key(item) for item in ads_items}

    google_total = len(google_items)
    semantic_total = len(semantic_items)
    ads_total = len(ads_items)
    semantic_extra = len([key for key in semantic_key_set if key not in google_key_set])
    ads_extra = len([key for key in ads_key_set if key not in (google_key_set | semantic_key_set)])
    total = len(google_key_set | semantic_key_set | ads_key_set)

    citations = {
        "google_scholar": citation_channel(
            ids=google_ids,
            url=google_url,
            citations=google_total,
        ),
        "semantic_scholar": citation_channel(
            identifier=semantic_id,
            url=semantic_url,
            citations=semantic_total,
            extra_non_duplicate=semantic_extra,
        ),
        "ads": citation_channel(
            identifier=ads_bibcode,
            url=ads_url,
            citations=ads_total,
            extra_non_duplicate=ads_extra,
        ),
        "total": total,
    }

    cache = {
        "google_scholar": {"documents": citation_item_list(google_items)},
        "semantic_scholar": {"documents": citation_item_list(semantic_items)},
        "ads": {"documents": citation_item_list(ads_items)},
    }
    return citations, cache


def yaml_indent(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line else line for line in text.splitlines())


def make_citations_block(citations: dict[str, Any]) -> str:
    dumped = yaml.safe_dump(citations, sort_keys=False, allow_unicode=True, width=1000).rstrip()
    return "  citations:\n" + yaml_indent(dumped, 4) + "\n"


def find_citations_span(lines: list[str]) -> tuple[int, int] | None:
    legacy_keys = {"google_scholar", "semantic_scholar", "ads", "total"}
    for index, line in enumerate(lines):
        if not re.match(r"^\s{2}citations:\s*$", line):
            continue

        end = index + 1
        while end < len(lines) and lines[end].strip() == "":
            end += 1

        if end >= len(lines):
            return index, end

        next_line = lines[end]
        if re.match(r"^\s{4}(google_scholar|semantic_scholar|ads|total):\s*$", next_line):
            end += 1
            while end < len(lines):
                if re.match(r"^\s{2}[A-Za-z0-9_.:-]+:\s*", lines[end]) or re.match(r"^[A-Za-z0-9_.:-]+:\s*", lines[end]):
                    break
                end += 1
            return index, end

        if re.match(r"^\s{2}(google_scholar|semantic_scholar|ads|total):\s*$", next_line):
            while end < len(lines):
                legacy_match = re.match(r"^\s{2}([A-Za-z0-9_.:-]+):\s*$", lines[end])
                if legacy_match and legacy_match.group(1) in legacy_keys:
                    end += 1
                    while end < len(lines) and not re.match(r"^\s{2}[A-Za-z0-9_.:-]+:\s*", lines[end]) and not re.match(r"^[A-Za-z0-9_.:-]+:\s*", lines[end]):
                        end += 1
                    continue
                if lines[end].strip() == "":
                    end += 1
                    continue
                break
            return index, end

        while end < len(lines):
            if re.match(r"^\s{2}[A-Za-z0-9_.:-]+:\s*", lines[end]) or re.match(r"^[A-Za-z0-9_.:-]+:\s*", lines[end]):
                break
            end += 1
        return index, end

    return None


def replace_or_insert_citations_block(block_text: str, citations: dict[str, Any]) -> str:
    lines = block_text.rstrip("\n").splitlines()
    existing_span = find_citations_span(lines)
    citations_block = make_citations_block(citations).rstrip("\n").splitlines()
    if existing_span is not None:
        start, end = existing_span
        lines[start:end] = citations_block
        return "\n".join(lines) + "\n"

    insert_index = len(lines)
    for field_name in ("abstract", "author_marks", "selected", "bibtex_show"):
        for index, line in enumerate(lines):
            if re.match(rf"^\s{{2}}{re.escape(field_name)}:\s*", line):
                insert_index = index
                break
        if insert_index != len(lines):
            break

    lines[insert_index:insert_index] = citations_block
    return "\n".join(lines) + "\n"


def update_publications_file(
    path: Path,
    articles_by_title: dict[str, dict[str, Any]] | None,
    serpapi_key: str,
    semantic_scholar_key: str | None,
    ads_token: str,
) -> tuple[bool, dict[str, dict[str, Any]]]:
    original = path.read_text(encoding="utf-8")
    blocks = find_publication_blocks(original)
    metadata = bib_metadata_by_key()
    existing_cache_by_paper = load_existing_cited_documents()

    rebuilt_parts: list[str] = []
    cursor = 0
    changed = False
    cache_by_paper: dict[str, dict[str, Any]] = {}

    for block in blocks:
        rebuilt_parts.append(original[cursor:block.start])
        cursor = block.end

        publication = parse_publication(block)
        bib_metadata = metadata.get(block.key)
        if not publication_has_citation_config(publication):
            rebuilt_parts.append(block.text)
            continue

        cache_by_paper[block.key] = existing_cache_by_paper.get(block.key, empty_cited_documents_entry())

        if not publication or bib_metadata is None:
            rebuilt_parts.append(block.text)
            continue

        try:
            citations, cache = generate_publication_citations(
                publication,
                bib_metadata,
                articles_by_title,
                serpapi_key,
                semantic_scholar_key,
                ads_token,
            )
        except Exception as error:
            print(f"Warning: skipping citation update for {block.key}: {error}", file=sys.stderr)
            rebuilt_parts.append(block.text)
            continue

        cache_by_paper[block.key] = cache

        new_block_text = replace_or_insert_citations_block(block.text, citations)
        changed = changed or new_block_text != block.text
        rebuilt_parts.append(new_block_text)

    rebuilt_parts.append(original[cursor:])
    if changed:
        path.write_text("".join(rebuilt_parts), encoding="utf-8")

    return changed, cache_by_paper


def write_cited_documents(cache_by_paper: dict[str, dict[str, Any]]) -> None:
    data = {
        "metadata": {"last_updated": time.strftime("%Y-%m-%d")},
        "papers": cache_by_paper,
    }
    CITED_DOCUMENTS_PATH.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=1000),
        encoding="utf-8",
    )


def main() -> int:
    serpapi_key = load_env("SERPAPI_API_KEY")
    ads_token = load_env("ADS_API_TOKEN")
    semantic_scholar_key = load_env("SEMANTIC_SCHOLAR_API_KEY")

    if not serpapi_key:
        print("SERPAPI_API_KEY is not set; skipping citation update.")
        return 0
    if not ads_token:
        print("ADS_API_TOKEN is not set; skipping citation update.")
        return 0

    scholar_user_id = load_scholar_user_id()
    print(f"Fetching Google Scholar author data for {scholar_user_id} via SerpApi")

    try:
        articles = fetch_google_author_articles(scholar_user_id, serpapi_key)
        articles_by_title = index_articles_by_title(articles)
        print(f"Fetched {len(articles)} Scholar author articles")
    except Exception as error:
        articles_by_title = None
        print(
            f"Warning: failed to fetch Scholar author data; title fallback is disabled for this run: {error}",
            file=sys.stderr,
        )

    changed, cache_by_paper = update_publications_file(
        PUBLICATIONS_PATH,
        articles_by_title,
        serpapi_key,
        semantic_scholar_key,
        ads_token,
    )
    write_cited_documents(cache_by_paper)

    print("Updated citation counts." if changed else "Citation counts already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
