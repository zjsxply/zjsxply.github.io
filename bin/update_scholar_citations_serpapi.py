#!/usr/bin/env python3
"""Update publication citation badges from Google Scholar and Semantic Scholar.

Google Scholar data is fetched through SerpApi. Semantic Scholar data is fetched
through the Semantic Scholar Graph API. For each publication, the script fetches
the citing-paper lists from both sources and deduplicates them before writing a
merged citation count to _data/publications.yml.
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

BIB_PATH = Path("_bibliography/papers.bib")
PUBLICATIONS_PATH = Path("_data/publications.yml")
SOCIALS_PATH = Path("_data/socials.yml")
SERPAPI_URL = "https://serpapi.com/search.json"
SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1"

CITATION_FETCH_LIMIT = int(os.environ.get("CITATION_FETCH_LIMIT", "500"))
SERPAPI_CITATION_PAGE_SIZE = int(os.environ.get("SERPAPI_CITATION_PAGE_SIZE", "20"))
SEMANTIC_SCHOLAR_CITATION_PAGE_SIZE = min(
    int(os.environ.get("SEMANTIC_SCHOLAR_CITATION_PAGE_SIZE", "100")),
    1000,
)
HTTP_429_RETRIES = int(os.environ.get("HTTP_429_RETRIES", "120"))
HTTP_429_RETRY_DELAY_SECONDS = float(os.environ.get("HTTP_429_RETRY_DELAY_SECONDS", "1"))


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
class CitationRecord:
    source: str
    title: str | None
    url: str | None
    external_ids: dict[str, str]
    source_id: str | None = None


@dataclass(frozen=True)
class PublicationCitationMetrics:
    scholar_citation_ids: list[str]
    scholar_citations: int | None
    semantic_scholar_paper_id: str | None
    semantic_scholar_url: str | None
    semantic_scholar_citations: int | None
    combined_citations: int | None


def load_scholar_user_id() -> str:
    if not SOCIALS_PATH.exists():
        raise FileNotFoundError(f"Missing {SOCIALS_PATH}")

    for line in SOCIALS_PATH.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*scholar_userid\s*:\s*([^#\s]+)", line)
        if match:
            return match.group(1).strip().strip('"\'')

    raise ValueError(f"Could not find scholar_userid in {SOCIALS_PATH}")


def fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> dict:
    request_headers = {"User-Agent": "zjsxply-citation-updater/1.0"}
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

    raise RuntimeError(f"Failed to fetch {url}")


def fetch_serpapi(params: dict[str, str]) -> dict:
    url = f"{SERPAPI_URL}?{urllib.parse.urlencode(params)}"
    payload = fetch_json(url)
    if "error" in payload:
        raise RuntimeError(f"SerpApi error: {payload['error']}")
    return payload


def fetch_semantic_scholar(path: str, params: dict[str, str], api_key: str | None) -> dict:
    url = f"{SEMANTIC_SCHOLAR_API_URL}{path}?{urllib.parse.urlencode(params)}"
    headers = {"x-api-key": api_key} if api_key else None
    payload = fetch_json(url, headers=headers)
    if "error" in payload:
        raise RuntimeError(f"Semantic Scholar error: {payload['error']}")
    return payload


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


def extract_yaml_scalar(block_text: str, field_name: str) -> str | None:
    match = re.search(rf"(?m)^\s{{2}}{re.escape(field_name)}:\s*(.*?)\s*$", block_text)
    if not match:
        return None
    return match.group(1).strip().strip('"\'')


def split_scholar_citation_ids(value: str) -> list[str]:
    return [part.strip().strip('"\'') for part in value.split(",") if part.strip()]


def parse_yaml_inline_list(value: str) -> list[str] | None:
    value = value.strip()
    if not value.startswith("[") or not value.endswith("]"):
        return None

    inner = value[1:-1].strip()
    if not inner:
        return []

    return split_scholar_citation_ids(inner)


def extract_yaml_values(block_text: str, field_name: str) -> list[str] | None:
    lines = block_text.splitlines()
    field_pattern = re.compile(rf"^\s{{2}}{re.escape(field_name)}:\s*(.*?)\s*$")
    item_pattern = re.compile(r"^\s{4}-\s*(.*?)\s*$")

    for index, line in enumerate(lines):
        match = field_pattern.match(line)
        if not match:
            continue

        value = match.group(1).strip()
        inline_values = parse_yaml_inline_list(value)
        if inline_values is not None:
            return inline_values
        if value:
            return split_scholar_citation_ids(value)

        values: list[str] = []
        for item_line in lines[index + 1 :]:
            if item_line.strip() == "":
                continue

            item_match = item_pattern.match(item_line)
            if not item_match:
                break

            values.extend(split_scholar_citation_ids(item_match.group(1)))

        return values

    return None


def extract_scholar_citation_ids(block_text: str) -> list[str]:
    citation_ids: list[str] = []

    multiple_ids = extract_yaml_values(block_text, "scholar_citation_ids")
    if multiple_ids is not None:
        citation_ids.extend(multiple_ids)

    normalized_ids: list[str] = []
    seen: set[str] = set()
    for citation_id in citation_ids:
        if not re.fullmatch(r"\d+", citation_id):
            raise ValueError(f"Invalid Scholar cites ID: {citation_id}")
        if citation_id not in seen:
            normalized_ids.append(citation_id)
            seen.add(citation_id)

    return normalized_ids


def normalize_title(title: str | None) -> str:
    if not title:
        return ""

    replacements = {
        r"\emph": " ",
        r"\textbf": " ",
        r"\textit": " ",
        "{": " ",
        "}": " ",
    }
    normalized = title
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
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


def bib_metadata_by_key() -> dict[str, BibMetadata]:
    original = BIB_PATH.read_text(encoding="utf-8")
    entries = find_bib_entries(original)
    metadata: dict[str, BibMetadata] = {}
    for entry in entries:
        metadata[entry.key] = BibMetadata(
            title=extract_field(entry.text, "title"),
            eprint=extract_field(entry.text, "eprint"),
            doi=extract_field(entry.text, "doi"),
            url=extract_field(entry.text, "url"),
        )
    return metadata


def yaml_scalar(value: int | str) -> str:
    if isinstance(value, int):
        return str(value)
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def find_yaml_field_span(lines: list[str], field_name: str) -> tuple[int, int] | None:
    field_pattern = re.compile(rf"^\s{{2}}{re.escape(field_name)}:\s*")
    next_field_pattern = re.compile(r"^\s{2}[A-Za-z0-9_.:-]+:\s*")
    next_block_pattern = re.compile(r"^[A-Za-z0-9_.:-]+:\s*")

    for index, line in enumerate(lines):
        if not field_pattern.match(line):
            continue

        end = index + 1
        while end < len(lines):
            if next_field_pattern.match(lines[end]) or next_block_pattern.match(lines[end]):
                break
            end += 1
        return index, end

    return None


def set_yaml_scalar_field(
    block_text: str,
    field_name: str,
    value: int | str,
    insert_after_fields: list[str],
) -> str:
    lines = block_text.splitlines()
    field_line = f"  {field_name}: {yaml_scalar(value)}"
    existing_span = find_yaml_field_span(lines, field_name)
    if existing_span:
        start, end = existing_span
        lines[start:end] = [field_line]
    else:
        insert_index = len(lines)
        for insert_after_field in insert_after_fields:
            span = find_yaml_field_span(lines, insert_after_field)
            if span:
                insert_index = span[1]
        lines.insert(insert_index, field_line)

    return "\n".join(lines) + ("\n" if block_text.endswith("\n") else "")


def set_yaml_list_field(
    block_text: str,
    field_name: str,
    values: list[str],
    insert_after_fields: list[str],
) -> str:
    lines = block_text.splitlines()
    field_lines = [f"  {field_name}:"] + [f"    - {yaml_scalar(value)}" for value in values]
    existing_span = find_yaml_field_span(lines, field_name)
    if existing_span:
        start, end = existing_span
        lines[start:end] = field_lines
    else:
        insert_index = len(lines)
        for insert_after_field in insert_after_fields:
            span = find_yaml_field_span(lines, insert_after_field)
            if span:
                insert_index = span[1]
        lines[insert_index:insert_index] = field_lines

    return "\n".join(lines) + ("\n" if block_text.endswith("\n") else "")


def remove_yaml_field(block_text: str, field_name: str) -> str:
    lines = block_text.splitlines()
    existing_span = find_yaml_field_span(lines, field_name)
    if not existing_span:
        return block_text

    start, end = existing_span
    del lines[start:end]
    return "\n".join(lines) + ("\n" if block_text.endswith("\n") else "")


def iter_strings(value: object) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for child in value.values():
            strings.extend(iter_strings(child))
    elif isinstance(value, list):
        for child in value:
            strings.extend(iter_strings(child))
    return strings


def extract_external_ids_from_strings(strings: list[str]) -> dict[str, str]:
    text = " ".join(strings)
    external_ids: dict[str, str] = {}

    doi_match = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, flags=re.IGNORECASE)
    if doi_match:
        external_ids["DOI"] = normalize_doi(doi_match.group(0))

    arxiv_match = re.search(
        r"(?i)(?:arxiv[:\s]+|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5}(?:v\d+)?)",
        text,
    )
    if arxiv_match:
        external_ids["ArXiv"] = normalize_arxiv_id(arxiv_match.group(1))

    return external_ids


def citation_record_from_serpapi_result(result: dict) -> CitationRecord:
    external_ids = extract_external_ids_from_strings(iter_strings(result))
    title = result.get("title") if isinstance(result.get("title"), str) else None
    link = result.get("link") if isinstance(result.get("link"), str) else None
    result_id = result.get("result_id") if isinstance(result.get("result_id"), str) else None
    return CitationRecord(source="google", title=title, url=link, external_ids=external_ids, source_id=result_id)


def citation_record_from_semantic_scholar_item(item: dict) -> CitationRecord | None:
    paper = item.get("citingPaper")
    if not isinstance(paper, dict):
        return None

    external_ids: dict[str, str] = {}
    raw_external_ids = paper.get("externalIds")
    if isinstance(raw_external_ids, dict):
        for key, value in raw_external_ids.items():
            if value is not None:
                external_ids[str(key)] = str(value)

    paper_id = paper.get("paperId")
    if paper_id:
        external_ids["SemanticScholar"] = str(paper_id)
    corpus_id = paper.get("corpusId")
    if corpus_id:
        external_ids["CorpusId"] = str(corpus_id)

    title = paper.get("title") if isinstance(paper.get("title"), str) else None
    url = paper.get("url") if isinstance(paper.get("url"), str) else None
    return CitationRecord(
        source="semantic_scholar",
        title=title,
        url=url,
        external_ids=external_ids,
        source_id=str(paper_id) if paper_id else None,
    )


def citation_record_keys(record: CitationRecord) -> set[str]:
    keys: set[str] = set()

    for raw_name, raw_value in record.external_ids.items():
        name = raw_name.lower()
        value = str(raw_value).strip()
        if not value:
            continue
        if name == "doi":
            keys.add(f"doi:{normalize_doi(value)}")
        elif name in {"arxiv", "arxiv_id"}:
            keys.add(f"arxiv:{normalize_arxiv_id(value)}")
        elif name in {"corpusid", "corpus_id"}:
            keys.add(f"corpus:{value}")
        elif name in {"semanticscholar", "paperid", "paper_id"}:
            keys.add(f"s2:{value.lower()}")
        else:
            keys.add(f"{name}:{value.lower()}")

    normalized_title = normalize_title(record.title)
    if len(normalized_title) >= 8:
        keys.add(f"title:{normalized_title}")

    normalized_url = normalize_url(record.url)
    if normalized_url:
        keys.add(f"url:{normalized_url}")

    if record.source_id:
        keys.add(f"{record.source}:id:{record.source_id}")

    return keys


def deduplicate_citation_records(records: list[CitationRecord]) -> int:
    if not records:
        return 0

    parent = list(range(len(records)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    key_owner: dict[str, int] = {}
    for index, record in enumerate(records):
        for key in citation_record_keys(record):
            owner = key_owner.get(key)
            if owner is None:
                key_owner[key] = index
            else:
                union(index, owner)

    return len({find(index) for index in range(len(records))})


def extract_cites_id(url: str) -> str | None:
    values = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("cites")
    if not values:
        return None
    return values[0]


def article_scholar_citation_id(article: dict) -> str | None:
    cited_by = article.get("cited_by")
    if not isinstance(cited_by, dict):
        return None

    for link_field in ("link", "serpapi_link"):
        link = cited_by.get(link_field)
        if isinstance(link, str):
            cites_id = extract_cites_id(link)
            if cites_id:
                return cites_id

    return None


def index_articles_by_title(articles: list[dict]) -> dict[str, dict]:
    by_title: dict[str, dict] = {}

    for article in articles:
        title = article.get("title")
        if not isinstance(title, str):
            continue

        normalized_title = normalize_title(title)
        if normalized_title in by_title:
            raise ValueError(f"Duplicate SerpApi article title after normalization: {title}")
        by_title[normalized_title] = article

    return by_title


def fetch_serpapi_author_articles(author_id: str, api_key: str) -> list[dict]:
    articles: list[dict] = []
    start = 0
    page_size = 100

    while True:
        payload = fetch_serpapi(
            {
                "engine": "google_scholar_author",
                "author_id": author_id,
                "hl": "en",
                "num": str(page_size),
                "start": str(start),
                "api_key": api_key,
            }
        )

        page_articles = payload.get("articles") or []
        articles.extend(page_articles)

        if len(page_articles) < page_size:
            break
        start += page_size
        if start >= 500:
            raise RuntimeError("Refusing to fetch more than 500 Scholar author articles")

    return articles


def fetch_serpapi_citing_records(citation_ids: list[str], api_key: str) -> list[CitationRecord]:
    records: list[CitationRecord] = []
    start = 0
    total_results: int | None = None

    while True:
        payload = fetch_serpapi(
            {
                "engine": "google_scholar",
                "cites": ",".join(citation_ids),
                "hl": "en",
                "num": str(SERPAPI_CITATION_PAGE_SIZE),
                "start": str(start),
                "api_key": api_key,
            }
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
            if isinstance(result, dict):
                records.append(citation_record_from_serpapi_result(result))

        if not page_results:
            break
        if total_results is not None and len(records) >= total_results:
            break
        if len(records) >= CITATION_FETCH_LIMIT:
            raise RuntimeError(
                f"Google Scholar cites={','.join(citation_ids)} exceeded CITATION_FETCH_LIMIT={CITATION_FETCH_LIMIT}"
            )

        start += len(page_results)

    return records


def semantic_scholar_paper_path(paper_id: str, suffix: str = "") -> str:
    return f"/paper/{urllib.parse.quote(paper_id, safe='')}{suffix}"


def semantic_scholar_headers_api_key() -> str | None:
    return os.environ.get("SEMANTIC_SCHOLAR_API_KEY") or os.environ.get("S2_API_KEY")


def resolve_semantic_scholar_paper_id(block_text: str, bib_metadata: BibMetadata | None) -> str | None:
    paper_id = extract_yaml_scalar(block_text, "semantic_scholar_paper_id")
    if paper_id:
        return paper_id

    paper_id = extract_yaml_scalar(block_text, "semantic_scholar_id")
    if paper_id:
        return paper_id

    if bib_metadata and bib_metadata.eprint:
        return f"arXiv:{normalize_arxiv_id(bib_metadata.eprint)}"

    doi = extract_yaml_scalar(block_text, "doi") or (bib_metadata.doi if bib_metadata else None)
    if doi:
        return f"DOI:{normalize_doi(doi)}"

    return None


def fetch_semantic_scholar_paper(paper_id: str, api_key: str | None) -> dict:
    return fetch_semantic_scholar(
        semantic_scholar_paper_path(paper_id),
        {
            "fields": "paperId,corpusId,title,externalIds,citationCount,url",
        },
        api_key,
    )


def fetch_semantic_scholar_citing_records(paper_id: str, api_key: str | None) -> list[CitationRecord]:
    records: list[CitationRecord] = []
    offset = 0

    while True:
        payload = fetch_semantic_scholar(
            semantic_scholar_paper_path(paper_id, "/citations"),
            {
                "fields": "citingPaper.paperId,citingPaper.corpusId,citingPaper.title,citingPaper.externalIds,citingPaper.year,citingPaper.url",
                "limit": str(SEMANTIC_SCHOLAR_CITATION_PAGE_SIZE),
                "offset": str(offset),
            },
            api_key,
        )

        page_items = payload.get("data") or []
        for item in page_items:
            if isinstance(item, dict):
                record = citation_record_from_semantic_scholar_item(item)
                if record:
                    records.append(record)

        next_offset = payload.get("next")
        if next_offset is None:
            break
        if len(records) >= CITATION_FETCH_LIMIT:
            raise RuntimeError(
                f"Semantic Scholar paper {paper_id} exceeded CITATION_FETCH_LIMIT={CITATION_FETCH_LIMIT}"
            )

        offset = int(next_offset)

    return records


def resolve_scholar_citation_ids(
    block: PublicationBlock,
    block_text: str,
    bib_metadata: BibMetadata | None,
    articles_by_title: dict[str, dict] | None,
) -> list[str] | None:
    scholar_citation_ids = extract_scholar_citation_ids(block_text)
    if scholar_citation_ids:
        return scholar_citation_ids

    if articles_by_title is None:
        return None

    if not bib_metadata or not bib_metadata.title:
        return []

    article = articles_by_title.get(normalize_title(bib_metadata.title))
    if not article:
        return []

    scholar_citation_id = article_scholar_citation_id(article)
    if not scholar_citation_id:
        return []

    return [scholar_citation_id]


def compute_publication_metrics(
    block: PublicationBlock,
    block_text: str,
    bib_metadata: BibMetadata | None,
    articles_by_title: dict[str, dict] | None,
    serpapi_key: str,
    semantic_scholar_key: str | None,
) -> PublicationCitationMetrics:
    records: list[CitationRecord] = []

    resolved_scholar_citation_ids = resolve_scholar_citation_ids(block, block_text, bib_metadata, articles_by_title)
    scholar_citation_ids = resolved_scholar_citation_ids or []
    scholar_citations: int | None = None
    if resolved_scholar_citation_ids is None:
        raise RuntimeError("Scholar author data unavailable and no scholar_citation_ids were configured")
    elif scholar_citation_ids:
        scholar_records = fetch_serpapi_citing_records(scholar_citation_ids, serpapi_key)
        scholar_citations = len(scholar_records)
        records.extend(scholar_records)
    else:
        scholar_citations = 0

    semantic_scholar_paper_id = resolve_semantic_scholar_paper_id(block_text, bib_metadata)
    semantic_scholar_url: str | None = extract_yaml_scalar(block_text, "semantic_scholar_url")
    semantic_scholar_citations: int | None = None
    if semantic_scholar_paper_id:
        paper = fetch_semantic_scholar_paper(semantic_scholar_paper_id, semantic_scholar_key)
        if isinstance(paper.get("url"), str):
            semantic_scholar_url = paper["url"]

        semantic_records = fetch_semantic_scholar_citing_records(semantic_scholar_paper_id, semantic_scholar_key)
        semantic_scholar_citations = len(semantic_records)
        records.extend(semantic_records)

    combined_citations = deduplicate_citation_records(records) if records else None

    return PublicationCitationMetrics(
        scholar_citation_ids=scholar_citation_ids,
        scholar_citations=scholar_citations,
        semantic_scholar_paper_id=semantic_scholar_paper_id,
        semantic_scholar_url=semantic_scholar_url,
        semantic_scholar_citations=semantic_scholar_citations,
        combined_citations=combined_citations,
    )


def publication_needs_citation_update(block_text: str) -> bool:
    return any(
        extract_yaml_scalar(block_text, field_name) is not None
        for field_name in (
            "scholar_citation_ids",
            "scholar_citations",
            "semantic_scholar_paper_id",
            "semantic_scholar_id",
            "semantic_scholar_citations",
            "combined_citations",
        )
    )


def update_publication_block(block_text: str, metrics: PublicationCitationMetrics) -> str:
    updated = remove_yaml_field(block_text, "scholar_citation_id")

    if metrics.scholar_citations is not None:
        if metrics.scholar_citation_ids:
            updated = set_yaml_list_field(
                updated,
                "scholar_citation_ids",
                metrics.scholar_citation_ids,
                ["github_repo", "code", "title_url", "title_logo"],
            )
        if metrics.scholar_citations > 0:
            updated = set_yaml_scalar_field(
                updated,
                "scholar_citations",
                metrics.scholar_citations,
                ["scholar_citation_ids"],
            )
        else:
            updated = remove_yaml_field(updated, "scholar_citations")

    if metrics.semantic_scholar_citations is not None and metrics.semantic_scholar_paper_id:
        updated = set_yaml_scalar_field(
            updated,
            "semantic_scholar_paper_id",
            metrics.semantic_scholar_paper_id,
            ["scholar_citations", "scholar_citation_ids"],
        )
        if metrics.semantic_scholar_url:
            updated = set_yaml_scalar_field(
                updated,
                "semantic_scholar_url",
                metrics.semantic_scholar_url,
                ["semantic_scholar_paper_id"],
            )
        updated = set_yaml_scalar_field(
            updated,
            "semantic_scholar_citations",
            metrics.semantic_scholar_citations,
            ["semantic_scholar_url", "semantic_scholar_paper_id"],
        )

    if metrics.combined_citations is not None:
        updated = set_yaml_scalar_field(
            updated,
            "combined_citations",
            metrics.combined_citations,
            ["semantic_scholar_citations", "scholar_citations"],
        )

    return updated


def update_publication_data(articles: list[dict] | None, serpapi_key: str, semantic_scholar_key: str | None) -> bool:
    original = PUBLICATIONS_PATH.read_text(encoding="utf-8")
    blocks = find_publication_blocks(original)
    metadata = bib_metadata_by_key()
    articles_by_title = index_articles_by_title(articles) if articles is not None else None

    rebuilt_parts: list[str] = []
    cursor = 0
    changed = False
    skipped_blocks: list[str] = []

    for block in blocks:
        rebuilt_parts.append(original[cursor:block.start])
        block_text = block.text
        cursor = block.end

        if not publication_needs_citation_update(block_text):
            rebuilt_parts.append(block_text)
            continue

        try:
            metrics = compute_publication_metrics(
                block,
                block_text,
                metadata.get(block.key),
                articles_by_title,
                serpapi_key,
                semantic_scholar_key,
            )
        except Exception as error:
            skipped_blocks.append(f"{block.key}: {error}")
            print(f"Warning: skipping citation update for {block.key}: {error}", file=sys.stderr)
            rebuilt_parts.append(block_text)
            continue

        print(
            f"{block.key}: combined={metrics.combined_citations}, "
            f"google={metrics.scholar_citations}, s2={metrics.semantic_scholar_citations}"
        )
        new_block_text = update_publication_block(block_text, metrics)
        if new_block_text != block_text:
            changed = True
        rebuilt_parts.append(new_block_text)

    rebuilt_parts.append(original[cursor:])
    if skipped_blocks:
        print("Skipped citation updates:\n- " + "\n- ".join(skipped_blocks), file=sys.stderr)

    updated = "".join(rebuilt_parts)
    if changed:
        PUBLICATIONS_PATH.write_text(updated, encoding="utf-8")
    return changed


def main() -> int:
    serpapi_key = os.environ.get("SERPAPI_API_KEY")
    if not serpapi_key:
        print("SERPAPI_API_KEY is not set; skipping citation update.")
        return 0

    author_id = os.environ.get("GOOGLE_SCHOLAR_ID") or load_scholar_user_id()
    print(f"Fetching Google Scholar author data for {author_id} via SerpApi")
    try:
        articles = fetch_serpapi_author_articles(author_id, serpapi_key)
    except Exception as error:
        articles = None
        print(
            f"Warning: failed to fetch Scholar author data; title fallback is disabled for this run: {error}",
            file=sys.stderr,
        )
    else:
        print(f"Fetched {len(articles)} Scholar author articles")

    semantic_scholar_key = semantic_scholar_headers_api_key()
    if not semantic_scholar_key:
        print("SEMANTIC_SCHOLAR_API_KEY is not set; using anonymous Semantic Scholar API access.")

    changed = update_publication_data(articles, serpapi_key, semantic_scholar_key)
    print("Updated citation counts." if changed else "Citation counts already up to date.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
