#!/usr/bin/env python3
"""Update publication citation data from Google Scholar, Semantic Scholar, and ADS.

The script rewrites `_data/publications.yml` with a nested `citations` structure
and writes per-source cited-paper caches to `_data/publication_cited_documents.yml`.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
HTTP_ATTEMPTS = 5
MAX_API_PAGES = 100
MAX_SCHOLAR_AUTHOR_ARTICLES = 500


@dataclass(frozen=True)
class BibEntry:
    key: str
    text: str


@dataclass(frozen=True)
class BibMetadata:
    title: str | None
    eprint: str | None
    doi: str | None


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
    arxiv_id: str | None = None
    doi: str | None = None
    title_aliases: tuple[str, ...] = ()


@dataclass
class UpdateSummary:
    citation_configured: int = 0
    updated: int = 0
    failed: int = 0
    partial: int = 0


def load_env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def log(message: str) -> None:
    print(redact_url(message).replace("\r", " ").replace("\n", " "), flush=True)


def warn(message: str) -> None:
    message = redact_url(message)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        message = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    prefix = "::warning::" if os.environ.get("GITHUB_ACTIONS") == "true" else "Warning: "
    print(f"{prefix}{message}", file=sys.stderr, flush=True)


def redact_url(url: str) -> str:
    for name in ("SERPAPI_API_KEY", "ADS_API_TOKEN", "SEMANTIC_SCHOLAR_API_KEY"):
        secret = load_env(name)
        if secret:
            url = url.replace(secret, "***").replace(urllib.parse.quote(secret, safe=""), "***")
    return re.sub(r"(?i)([?&](?:api_key|api_token|token)=)[^&\s]+", r"\1***", url)


class ApiError(RuntimeError):
    pass


class NoScholarResults(ApiError):
    pass


def fetch_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    request_headers = {"User-Agent": "zjsxply-citation-updater/3.0"}
    if headers:
        request_headers.update(headers)

    endpoint = urllib.parse.urlsplit(url)
    label = f"{endpoint.netloc}{endpoint.path}"
    for attempt in range(HTTP_ATTEMPTS):
        request = urllib.request.Request(url, headers=request_headers)
        retry_after = None
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ApiError(f"{label}: expected a JSON object")
                error = payload.get("error")
                if error:
                    if endpoint.netloc == "serpapi.com" and error == "Google hasn't returned any results for this query.":
                        raise NoScholarResults(str(error))
                    raise ApiError(redact_url(f"{label}: {error}"))
                if attempt:
                    log(f"{label}: recovered after {attempt} retry/retries.")
                return payload
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")[:500]
            reason = redact_url(f"HTTP {error.code}: {body}")
            if error.code not in {408, 429, 500, 502, 503, 504}:
                raise ApiError(f"{label}: {reason}") from None
            retry_after = error.headers.get("Retry-After") if error.headers else None
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException,
                json.JSONDecodeError, UnicodeDecodeError) as error:
            reason = redact_url(f"{type(error).__name__}: {error}")
        if attempt == HTTP_ATTEMPTS - 1:
            raise ApiError(f"{label}: failed after {HTTP_ATTEMPTS} attempts; {reason}")
        delay = min(2 ** (attempt + 1), 30)
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                try:
                    delay = max(delay, (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    pass
        if delay > 60:
            raise ApiError(f"{label}: server requested a {delay:g}s retry delay; defer this source to the next run")
        if attempt == 0:
            log(f"{label}: {reason}; retrying (at most {HTTP_ATTEMPTS} attempts).")
        time.sleep(delay)
    raise ApiError(f"{label}: request failed")


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
                    entries.append(BibEntry(key=key, text=text[at_index:end]))
                    index = end
                    break
            position += 1
        else:
            raise ValueError(f"Unbalanced BibTeX braces near byte offset {at_index}")

    return entries


def find_publication_blocks(text: str) -> list[PublicationBlock]:
    load_yaml_mapping(text)
    root = yaml.compose(text)
    if not isinstance(root, yaml.MappingNode) or root.flow_style:
        raise ValueError("Publications must be a block-style YAML mapping")
    blocks = []
    for index, (key, value) in enumerate(root.value):
        if not isinstance(key, yaml.ScalarNode) or key.tag != "tag:yaml.org,2002:str":
            raise ValueError("Publication keys must be strings")
        if not isinstance(value, yaml.MappingNode) or value.flow_style or value.start_mark.index < key.start_mark.index:
            raise ValueError(f"{key.value}: publication must be a block-style mapping, not an alias")
        start = key.start_mark.index
        end = root.value[index + 1][0].start_mark.index if index + 1 < len(root.value) else len(text)
        blocks.append(PublicationBlock(key=key.value, start=start, end=end, text=text[start:end]))
    return blocks


class UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
        keys = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in keys:
                raise ValueError(f"Duplicate YAML key: {key}")
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


def load_yaml_mapping(text: str) -> dict[str, Any]:
    data = yaml.load(text, Loader=UniqueKeyLoader)
    if not isinstance(data, dict):
        raise ValueError("Expected a YAML mapping")
    return data


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
        )
    return metadata


def normalize_title(title: str | None) -> str:
    if not title:
        return ""

    normalized = title
    for old in [r"\emph", r"\textbf", r"\textit", "{", "}"]:
        normalized = normalized.replace(old, " ")
    normalized = normalized.casefold()
    normalized = re.sub(r"[^\w+#]+|_", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_arxiv_id(arxiv_id: str) -> str:
    arxiv_id = re.sub(r"(?i)^arxiv:\s*", "", arxiv_id.strip())
    parsed = urllib.parse.urlparse(arxiv_id)
    if parsed.netloc.lower() in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        arxiv_id = re.sub(r"(?i)^/(?:abs|pdf|html)/", "", parsed.path)
    arxiv_id = arxiv_id.lower().removesuffix(".pdf")
    return re.sub(r"v\d+$", "", arxiv_id)


def normalize_doi(doi: str) -> str:
    doi = re.sub(r"(?i)^doi:\s*", "", doi.strip())
    parsed = urllib.parse.urlparse(doi)
    if parsed.netloc.lower() in {"doi.org", "dx.doi.org", "www.doi.org"}:
        doi = urllib.parse.unquote(parsed.path.lstrip("/"))
    return doi.lower()


def valid_arxiv_id(value: str | None) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = normalize_arxiv_id(value)
    if re.fullmatch(r"(?:[a-z][a-z0-9.-]*/\d{7}|\d{4}\.\d{4,5})", normalized):
        return normalized
    return None


def valid_doi(value: str | None) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = normalize_doi(value)
    return normalized if re.fullmatch(r"10\.\d{4,9}/\S+", normalized) else None


def arxiv_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.lower() not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        return None
    match = re.match(r"^/(?:abs|pdf|html)/(.+?)(?:\.pdf)?$", parsed.path, flags=re.IGNORECASE)
    return valid_arxiv_id(match.group(1)) if match else None


def doi_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.lower() not in {"doi.org", "dx.doi.org", "www.doi.org"}:
        return None
    return valid_doi(urllib.parse.unquote(parsed.path.lstrip("/")))


def arxiv_id_from_identifiers(identifiers: list[str]) -> str | None:
    for identifier in identifiers:
        normalized = valid_arxiv_id(identifier)
        if normalized:
            return normalized
    return None


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc:
        return None

    path = parsed.path.rstrip("/")
    return urllib.parse.urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.params, parsed.query, ""))


def article_title(article: dict[str, Any]) -> str | None:
    title = article.get("title")
    if isinstance(title, list) and title:
        title = title[0]
    return title if isinstance(title, str) else None


def citation_item_identifiers(item: CitationItem) -> set[tuple[str, str]]:
    identifiers: set[tuple[str, str]] = set()
    for arxiv_id in (valid_arxiv_id(item.arxiv_id), arxiv_id_from_url(item.link)):
        if arxiv_id:
            identifiers.add(("arxiv", arxiv_id))
    for doi in (valid_doi(item.doi), doi_from_url(item.link)):
        if not doi:
            continue
        arxiv_id = valid_arxiv_id(doi.removeprefix("10.48550/arxiv.")) if doi.startswith("10.48550/arxiv.") else None
        identifiers.add(("arxiv", arxiv_id) if arxiv_id else ("doi", doi))
    return identifiers


def citation_item_titles(item: CitationItem) -> tuple[str, ...]:
    return tuple(sorted(set((item.title, *item.title_aliases))))


def citation_item_evidence_key(item: CitationItem) -> str:
    """Identify records that can be compressed without losing grouping evidence."""
    identifiers = sorted(citation_item_identifiers(item))
    if identifiers:
        evidence: dict[str, Any] = {"identifiers": identifiers}
    else:
        titles = sorted({normalize_title(title) for title in citation_item_titles(item)} - {""})
        evidence = {"titles": titles}
        if not titles:
            evidence["raw_titles"] = citation_item_titles(item)
            evidence["link"] = normalize_url(item.link) or item.link
    return json.dumps(evidence, sort_keys=True)


def citation_identity_components(identity_sets: list[set[tuple[str, str]]]) -> list[list[int]]:
    parents = list(range(len(identity_sets)))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    owners: dict[tuple[str, str], int] = {}
    for index, identities in enumerate(identity_sets):
        for identity in sorted(identities):
            owner = owners.setdefault(identity, index)
            parents[root(index)] = root(owner)

    groups: dict[int, list[int]] = {}
    for index in range(len(identity_sets)):
        groups.setdefault(root(index), []).append(index)
    return list(groups.values())


def citation_identifiers_conflict(identifiers: set[tuple[str, str]]) -> bool:
    return any(sum(kind == namespace for kind, _ in identifiers) > 1 for namespace in ("arxiv", "doi"))


def citation_item_groups(items: list[CitationItem]) -> list[list[int]]:
    """Cluster strong IDs first, then unambiguous exact titles, without fuzzy edges.

    Conflicting strong components only deduplicate identical ID sets. A weak
    component is merged only as a whole: an ID-less title cannot bridge two
    conflicting works. Groups and members retain first-occurrence order.
    """
    identifiers = [citation_item_identifiers(item) for item in items]
    strong_keys = [
        identities | {("evidence", citation_item_evidence_key(item))}
        for item, identities in zip(items, identifiers)
    ]
    strong_groups: list[list[int]] = []
    blocked: set[int] = set()
    for group in citation_identity_components(strong_keys):
        combined = set().union(*(identifiers[index] for index in group))
        if not citation_identifiers_conflict(combined):
            strong_groups.append(group)
            continue
        by_identity: dict[tuple[tuple[str, str], ...], list[int]] = {}
        for index in group:
            by_identity.setdefault(tuple(sorted(identifiers[index])), []).append(index)
        for identical in by_identity.values():
            blocked.add(len(strong_groups))
            strong_groups.append(identical)

    # Resolve strong IDs first; title-only records must not bridge conflicting components.
    weak_identities: list[set[tuple[str, str]]] = []
    for group_index, group in enumerate(strong_groups):
        keys: set[tuple[str, str]] = set()
        if group_index not in blocked:
            for index in group:
                for title in citation_item_titles(items[index]):
                    normalized = normalize_title(title)
                    if normalized:
                        keys.add(("title", normalized))
        weak_identities.append(keys)

    result: list[list[int]] = []
    for component in citation_identity_components(weak_identities):
        groups = [strong_groups[index] for index in component]
        members = sorted(index for group in groups for index in group)
        combined = set().union(*(identifiers[index] for index in members))
        if citation_identifiers_conflict(combined):
            result.extend(groups)
        else:
            result.append(members)
    return sorted(result, key=lambda group: group[0])


def unique_items(items: list[CitationItem]) -> list[CitationItem]:
    """Compress identical evidence signatures, preserving aliases and input order.

    Partial-ID and title-only matches remain separate until counting, because a
    later source may introduce conflicting IDs. This compression is idempotent
    and preserves combined counts, including after serialization to the cache.
    """
    groups: dict[str, list[int]] = {}
    for index, item in enumerate(items):
        groups.setdefault(citation_item_evidence_key(item), []).append(index)
    ordered: list[CitationItem] = []
    for group in groups.values():
        preferred = max((items[index] for index in group), key=citation_item_preference)
        identifiers = set().union(*(citation_item_identifiers(items[index]) for index in group))
        arxiv_ids = sorted(value for kind, value in identifiers if kind == "arxiv")
        dois = sorted(value for kind, value in identifiers if kind == "doi")
        ordered.append(
            CitationItem(
                title=preferred.title,
                link=preferred.link,
                arxiv_id=arxiv_ids[0] if len(arxiv_ids) == 1 else preferred.arxiv_id,
                doi=dois[0] if len(dois) == 1 else preferred.doi,
                # Dropping aliases can hide conflicts and change counts after another dedup pass.
                title_aliases=tuple(
                    sorted({title for index in group for title in citation_item_titles(items[index])} - {preferred.title})
                ),
            )
        )
    return ordered


def citation_counts_by_source(source_lists: list[list[CitationItem]]) -> tuple[list[int], list[int], int]:
    """Return (source_totals, source_extras, union_total) from the same global groups."""
    items = [item for source in source_lists for item in source]
    sources = [source_index for source_index, source in enumerate(source_lists) for _ in source]
    totals = [0] * len(source_lists)
    extras = [0] * len(source_lists)
    groups = citation_item_groups(items)
    for group in groups:
        member_sources = {sources[index] for index in group}
        for source in member_sources:
            totals[source] += 1
        extras[min(member_sources)] += 1
    return totals, extras, len(groups)


def citation_item_preference(item: CitationItem) -> tuple[int, int, int]:
    return (
        int(bool(item.arxiv_id)),
        int(bool(item.doi)),
        len(normalize_title(item.title)),
    )


def citation_item_from_dict(document: Any) -> CitationItem | None:
    """Read one cache record; callers must reject incomplete source caches."""
    if not isinstance(document, dict):
        return None
    title = document.get("title")
    link = document.get("link")
    if not isinstance(title, str) or not title.strip() or not isinstance(link, str) or not link.strip():
        return None
    title, link = title.strip(), link.strip()
    try:
        parsed = urllib.parse.urlparse(link)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return None
        arxiv_id = valid_arxiv_id(document.get("arxiv_id")) or arxiv_id_from_url(link)
        doi = valid_doi(document.get("doi")) or doi_from_url(link)
    except ValueError:
        return None
    title_aliases = document.get("title_aliases")
    aliases = (
        tuple(sorted({title.strip() for title in title_aliases if isinstance(title, str) and title.strip()} - {title}))
        if isinstance(title_aliases, (list, tuple))
        else ()
    )
    return CitationItem(
        title=title,
        link=link,
        arxiv_id=arxiv_id,
        doi=doi,
        title_aliases=aliases,
    )


def item_dict(item: CitationItem) -> dict[str, Any]:
    document: dict[str, Any] = {"title": item.title, "link": item.link}
    if item.arxiv_id:
        document["arxiv_id"] = item.arxiv_id
    if item.doi:
        document["doi"] = item.doi
    if item.title_aliases:
        document["title_aliases"] = list(item.title_aliases)
    return document


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
    loaded = load_yaml_mapping(block.text)
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

    loaded = load_yaml_mapping(CITED_DOCUMENTS_PATH.read_text(encoding="utf-8"))
    papers = loaded.get("papers")
    if not isinstance(papers, dict):
        raise ValueError(f"{CITED_DOCUMENTS_PATH}: missing papers mapping")
    return papers


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
        return [str(item).strip() for item in value if item is not None and str(item).strip()]
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
    # Presence matters: ids: [] must not resurrect a stale ID from a legacy URL.
    if "ids" in google:
        value = google["ids"]
    elif "id" in google:
        value = google["id"]
    elif "scholar_citation_ids" in publication:
        value = publication["scholar_citation_ids"]
    else:
        value = extract_cites_ids_from_url(google.get("url"))
    ids = [part.strip() for item in as_string_list(value) for part in item.split(",") if part.strip()]
    if any(not identifier.isdigit() for identifier in ids):
        raise ValueError("Google Scholar citation IDs must be numeric")
    return list(dict.fromkeys(ids))


def has_explicit_google_id_config(publication: dict[str, Any]) -> bool:
    google = publication_source_section(publication, "google_scholar")
    if "ids" in google or "id" in google:
        return True
    if "scholar_citation_ids" in publication:
        return True
    return bool(extract_cites_ids_from_url(google.get("url")))


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
        page_articles = payload.get("articles")
        if not isinstance(page_articles, list):
            raise ApiError("Google Scholar author lookup: missing articles")
        for article in page_articles:
            if isinstance(article, dict):
                articles.append(article)

        if len(page_articles) < GOOGLE_AUTHOR_PAGE_SIZE:
            break

        start += GOOGLE_AUTHOR_PAGE_SIZE
        if start >= MAX_SCHOLAR_AUTHOR_ARTICLES:
            raise ApiError("Google Scholar author lookup exceeded the article limit")

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
    if has_explicit_google_id_config(publication):
        return []

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


def publications_needing_google_author_lookup(path: Path) -> list[str]:
    original = path.read_text(encoding="utf-8")
    metadata = bib_metadata_by_key()
    paper_keys: list[str] = []

    for block in find_publication_blocks(original):
        publication = parse_publication(block)
        if not publication_has_citation_config(publication):
            continue
        if normalize_google_ids(publication) or has_explicit_google_id_config(publication):
            continue
        bib_metadata = metadata.get(block.key)
        if bib_metadata and bib_metadata.title:
            paper_keys.append(block.key)

    return paper_keys


def fetch_serpapi_citing_items(cites_ids: list[str], api_key: str) -> list[CitationItem]:
    items: list[CitationItem] = []
    # Fetch each Scholar record independently; merged queries have returned incomplete lists.
    for cites_id in dict.fromkeys(cites_ids):
        items.extend(fetch_serpapi_citation_cluster(cites_id, api_key))
    return unique_items(items)


def next_scholar_page(payload: dict[str, Any], start: int, cites_id: str) -> dict[str, str] | None:
    for field in ("serpapi_pagination", "pagination"):
        pagination = payload.get(field) or {}
        if not isinstance(pagination, dict):
            raise ApiError("Google Scholar: malformed pagination")
        link = pagination.get("next") or pagination.get("next_link")
        if link:
            try:
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(link).query)
                offset = int(query["start"][0])
            except (KeyError, ValueError, TypeError):
                raise ApiError("Google Scholar: invalid next-page offset") from None
            if offset <= start:
                raise ApiError("Google Scholar: next-page offset did not advance")
            if query.get("cites", [cites_id]) != [cites_id]:
                raise ApiError("Google Scholar: next page changed citation ID")
            # Preserve Scholar's search context, but never follow a returned URL with our API key.
            allowed = {"start", "as_sdt", "sciodt", "scipsc", "filter"}
            return {name: values[0] for name, values in query.items() if name in allowed}
    return None


def fetch_serpapi_citation_cluster(cites_id: str, api_key: str) -> list[CitationItem]:
    items: list[CitationItem] = []
    start = 0
    expected_page = False
    # Use documented article scope and disable omitted-result filtering; deduplicate locally.
    page_params: dict[str, str] = {"as_sdt": "0", "filter": "0"}
    seen_pages: set[str] = set()
    for _ in range(MAX_API_PAGES):
        try:
            payload = fetch_serpapi(
                {"engine": "google_scholar", "cites": cites_id, "hl": "en",
                 "num": str(SERPAPI_CITATION_PAGE_SIZE), **page_params, "start": str(start)},
                api_key,
            )
        except NoScholarResults:
            if expected_page:
                raise ApiError(f"Google Scholar ID {cites_id}: advertised page at {start} returned no results") from None
            break
        page_results = payload.get("organic_results")
        if page_results is None and (payload.get("search_information") or {}).get("total_results") == 0:
            page_results = []
        if not isinstance(page_results, list):
            raise ApiError(f"Google Scholar ID {cites_id}: missing organic_results")
        next_page = next_scholar_page(payload, start, cites_id)
        if not page_results:
            if expected_page or next_page is not None:
                raise ApiError(f"Google Scholar ID {cites_id}: empty page before end of pagination")
            break
        signature = json.dumps(page_results, sort_keys=True)
        if signature in seen_pages:
            raise ApiError(f"Google Scholar ID {cites_id}: repeated page at {start}")
        seen_pages.add(signature)
        for result in page_results:
            if not isinstance(result, dict):
                raise ApiError("Google Scholar: malformed citing document")
            title = result.get("title")
            if not isinstance(title, str) or not title.strip():
                raise ApiError("Google Scholar: citing document has no title")
            link = result.get("link")
            if not isinstance(link, str) or not link.strip():
                link = "https://scholar.google.com/scholar?" + urllib.parse.urlencode({"q": f'"{title.strip()}"'})
            items.append(
                CitationItem(
                    title=title.strip(),
                    link=link.strip(),
                    arxiv_id=arxiv_id_from_url(link),
                    doi=doi_from_url(link),
                )
            )

        # Scholar has reported total_results=20 with more pages still available. A full
        # page without a next link needs a probe; an advertised page must not fail silently.
        if next_page is None and len(page_results) < SERPAPI_CITATION_PAGE_SIZE:
            break
        expected_page = next_page is not None
        if next_page is not None:
            page_params.update(next_page)
            start = int(next_page["start"])
        else:
            start += len(page_results)
    else:
        raise ApiError(f"Google Scholar ID {cites_id}: exceeded {MAX_API_PAGES} pages; refusing partial data")

    return unique_items(items)


def fetch_semantic_scholar_citing_items(paper_id: str, api_key: str | None) -> list[CitationItem]:
    if not paper_id:
        return []

    items: list[CitationItem] = []
    offset = 0

    seen_pages: set[str] = set()
    for _ in range(MAX_API_PAGES):
        payload = fetch_semantic_scholar(
            f"/paper/{urllib.parse.quote(paper_id, safe='')}/citations",
            {
                "fields": "citingPaper.paperId,citingPaper.title,citingPaper.url,citingPaper.externalIds",
                "limit": str(SEMANTIC_SCHOLAR_CITATION_PAGE_SIZE),
                "offset": str(offset),
            },
            api_key,
        )

        page_items = payload.get("data")
        if not isinstance(page_items, list):
            raise ApiError("Semantic Scholar: missing citation data")
        if payload.get("offset", offset) != offset:
            raise ApiError("Semantic Scholar: response offset does not match request")
        signature = json.dumps(page_items, sort_keys=True)
        if page_items and signature in seen_pages:
            raise ApiError("Semantic Scholar: repeated citation page")
        seen_pages.add(signature)
        for item in page_items:
            if not isinstance(item, dict):
                raise ApiError("Semantic Scholar: malformed citation record")
            citing = item.get("citingPaper")
            if not isinstance(citing, dict):
                raise ApiError("Semantic Scholar: missing citingPaper")
            title = citing.get("title")
            if not isinstance(title, str) or not title.strip():
                raise ApiError("Semantic Scholar: citing paper has no title")
            link = citing.get("url")
            if not isinstance(link, str) or not link.strip():
                paper_id_value = citing.get("paperId")
                if isinstance(paper_id_value, str) and paper_id_value.strip():
                    link = f"https://www.semanticscholar.org/paper/{paper_id_value.strip()}"
            if not isinstance(link, str) or not link.strip():
                raise ApiError("Semantic Scholar: citing paper has no URL or paperId")
            external_ids = citing.get("externalIds")
            if not isinstance(external_ids, dict):
                external_ids = {}
            arxiv_id = external_ids.get("ArXiv")
            doi = external_ids.get("DOI")
            items.append(
                CitationItem(
                    title=title.strip(),
                    link=link.strip(),
                    arxiv_id=valid_arxiv_id(arxiv_id) if isinstance(arxiv_id, str) else None,
                    doi=valid_doi(doi) if isinstance(doi, str) else None,
                )
            )

        next_offset = payload.get("next")
        if next_offset is None:
            break
        if not page_items or isinstance(next_offset, bool) or not str(next_offset).isdigit() or int(next_offset) <= offset:
            raise ApiError("Semantic Scholar: pagination did not advance")
        offset = int(next_offset)
    else:
        raise ApiError("Semantic Scholar: page limit reached; refusing partial data")

    return unique_items(items)


def ads_search_bibcode(query: str, token: str | None) -> str | None:
    if not token:
        return None
    payload = fetch_ads({"q": query, "fl": "bibcode", "rows": "1"}, token)
    response = payload.get("response")
    if not isinstance(response, dict) or not isinstance(response.get("docs"), list):
        raise ApiError("ADS: malformed bibcode search response")
    docs = response["docs"]
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

    seen_pages: set[str] = set()
    for _ in range(MAX_API_PAGES):
        payload = fetch_ads(
            {
                "q": f"citations({bibcode})",
                "fl": "bibcode,title,identifier",
                "rows": str(ADS_CITATION_PAGE_SIZE),
                "start": str(start),
            },
            token,
        )

        response = payload.get("response")
        if not isinstance(response, dict) or not isinstance(response.get("docs"), list):
            raise ApiError("ADS: malformed citation response")
        if total_results is None:
            raw_total = response.get("numFound")
            if isinstance(raw_total, int):
                total_results = raw_total
            elif isinstance(raw_total, str) and raw_total.isdigit():
                total_results = int(raw_total)
            if total_results is None or total_results < 0:
                raise ApiError("ADS: invalid numFound")

        docs = response["docs"]
        if response.get("start", start) != start:
            raise ApiError("ADS: response offset does not match request")
        signature = json.dumps(docs, sort_keys=True)
        if docs and signature in seen_pages:
            raise ApiError("ADS: repeated citation page")
        seen_pages.add(signature)
        for doc in docs:
            if not isinstance(doc, dict):
                raise ApiError("ADS: malformed citing document")
            title = doc.get("title")
            if isinstance(title, list) and title:
                title = title[0]
            if not isinstance(title, str) or not title.strip():
                raise ApiError("ADS: citing document has no title")
            cited_bibcode = doc.get("bibcode")
            if not isinstance(cited_bibcode, str) or not cited_bibcode.strip():
                raise ApiError("ADS: citing document has no bibcode")
            items.append(
                CitationItem(
                    title=title.strip(),
                    link=f"https://ui.adsabs.harvard.edu/abs/{cited_bibcode.strip()}/abstract",
                    arxiv_id=arxiv_id_from_identifiers(as_string_list(doc.get("identifier"))),
                    doi=next((identifier for raw in as_string_list(doc.get("identifier"))
                              if (identifier := valid_doi(raw))), None),
                )
            )

        start += len(docs)
        if start >= total_results:
            break
        if not docs:
            raise ApiError(f"ADS: only retrieved {start}/{total_results} citing documents")
    else:
        raise ApiError("ADS: page limit reached; refusing partial data")

    return unique_items(items)


def citation_item_sort_key(item: CitationItem) -> tuple[str, str, str]:
    return (normalize_title(item.title), item.title.casefold(), normalize_url(item.link) or item.link.casefold())


def citation_item_list(items: list[CitationItem]) -> list[dict[str, Any]]:
    return [item_dict(item) for item in sorted(items, key=citation_item_sort_key)]


def cached_source_items(cache: dict[str, Any], source: str) -> list[CitationItem]:
    section = cache.get(source)
    if not isinstance(section, dict) or not isinstance(section.get("documents"), list):
        raise ValueError(f"{source}: no usable cached documents")
    items = []
    for document in section["documents"]:
        item = citation_item_from_dict(document)
        if item is None:
            raise ValueError(f"{source}: invalid cached document")
        items.append(item)
    return items


def generate_publication_citations(
    publication: dict[str, Any],
    bib_metadata: BibMetadata | None,
    articles_by_title: dict[str, dict[str, Any]] | None,
    serpapi_key: str,
    semantic_scholar_key: str | None,
    ads_token: str,
    existing_cache: dict[str, Any] | None = None,
    paper_key: str = "publication",
    allow_decrease: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    existing_cache = existing_cache or {}
    stale_sources: list[str] = []
    unavailable_sources: list[str] = []
    queries: dict[str, Any] = {}

    def cache_matches(source: str) -> bool:
        section = existing_cache.get(source, {})
        if "query" not in section:
            return True
        previous, current = section["query"], queries.get(source)
        if source == "google_scholar" and isinstance(previous, list) and isinstance(current, list):
            return set(previous) == set(current)
        return previous == current

    def fetch_source(source: str, fetcher: Any) -> list[CitationItem]:
        old_count = publication_source_section(publication, source).get("citations", 0)
        if not isinstance(old_count, int) or isinstance(old_count, bool) or old_count < 0:
            raise ValueError(f"{paper_key}/{source}: invalid previous citation count")
        try:
            items = fetcher()
            if not cache_matches(source):
                return items
            cached = cached_source_items(existing_cache, source) if source in existing_cache else []
            cached_count = len(citation_item_groups(cached))
            previous_count = cached_count if existing_cache.get(source, {}).get("citations") == old_count else max(old_count, cached_count)
            current_count = len(citation_item_groups(items))
            if current_count < previous_count:
                covered = bool(cached) and citation_counts_by_source([items, cached])[1][1] == 0
                if covered:
                    log(f"{paper_key}/{source}: count {previous_count} -> {current_count} after deduplication; all cached works are still present.")
                elif not allow_decrease:
                    raise ApiError(
                        f"document count decreased {previous_count} -> {current_count}; "
                        "review the source and use --allow-decrease only if this is expected"
                    )
                else:
                    log(f"{paper_key}/{source}: accepting reviewed decrease {previous_count} -> {current_count}.")
            return items
        except (ApiError, ValueError) as error:
            stale_sources.append(source)
            try:
                # A failed source is unknown, not empty. Only reuse a complete cache for this query.
                if not cache_matches(source):
                    raise ValueError("cached source belongs to a different query ID")
                cached = cached_source_items(existing_cache, source)
                cached_count = existing_cache[source].get("citations", len(cached))
                if cached_count != old_count or len(cached) < old_count:
                    raise ValueError(f"cached count {cached_count} does not match saved count {old_count}")
            except ValueError as cache_error:
                unavailable_sources.append(source)
                warn(f"{paper_key}/{source}: {error}; {cache_error}; cannot refresh this paper.")
                return []
            warn(f"{paper_key}/{source}: {error}; retaining {len(cached)} cached documents.")
            return cached

    def fetch_google() -> list[CitationItem]:
        if not google_ids and not has_explicit_google_id_config(publication) and articles_by_title is None:
            raise ApiError("author lookup unavailable and no explicit citation IDs")
        return fetch_serpapi_citing_items(google_ids, serpapi_key)

    google_ids = resolve_google_ids(publication, bib_metadata, articles_by_title)
    queries["google_scholar"] = google_ids
    google_url = f"https://scholar.google.com/scholar?cites={','.join(google_ids)}" if google_ids else None
    google_items = fetch_source("google_scholar", fetch_google)

    semantic_id = normalize_semantic_id(publication, bib_metadata)
    queries["semantic_scholar"] = semantic_id
    semantic_url = None
    semantic = publication_source_section(publication, "semantic_scholar")
    raw_url = semantic.get("url")
    if isinstance(raw_url, str) and raw_url.strip():
        semantic_url = raw_url.strip()
    elif isinstance(publication.get("semantic_scholar_url"), str) and publication["semantic_scholar_url"].strip():
        semantic_url = publication["semantic_scholar_url"].strip()
    elif semantic_id:
        semantic_url = f"https://www.semanticscholar.org/paper/{urllib.parse.quote(semantic_id, safe='')}"
    semantic_items = fetch_source(
        "semantic_scholar", lambda: fetch_semantic_scholar_citing_items(semantic_id, semantic_scholar_key) if semantic_id else []
    )

    ads_bibcode = None
    queries["ads"] = resolve_ads_bibcode(publication, bib_metadata, None)

    def fetch_ads_items() -> list[CitationItem]:
        nonlocal ads_bibcode
        ads_bibcode = resolve_ads_bibcode(publication, bib_metadata, ads_token)
        queries["ads"] = ads_bibcode
        return fetch_ads_citing_items(ads_bibcode, ads_token) if ads_bibcode else []

    ads_items = fetch_source("ads", fetch_ads_items)
    if unavailable_sources:
        raise ApiError("No valid cache for " + ", ".join(unavailable_sources))
    if ads_bibcode is None and "ads" in stale_sources:
        ads_bibcode = resolve_ads_bibcode(publication, bib_metadata, None)
    ads = publication_source_section(publication, "ads")
    ads_url = None
    raw_ads_url = ads.get("url")
    if isinstance(raw_ads_url, str) and raw_ads_url.strip():
        ads_url = raw_ads_url.strip()
    elif ads_bibcode:
        ads_url = f"https://ui.adsabs.harvard.edu/abs/{ads_bibcode}/citations"

    google_items = unique_items(google_items)
    semantic_items = unique_items(semantic_items)
    ads_items = unique_items(ads_items)

    # Cache records retain identity evidence/variants; len(documents) is not a citation count.
    source_totals, extras, total = citation_counts_by_source([google_items, semantic_items, ads_items])
    google_total, semantic_total, ads_total = source_totals
    semantic_extra, ads_extra = extras[1:]

    citations = {
        "google_scholar": citation_channel(
            # An unresolved automatic lookup must remain retryable, unlike explicit ids: [].
            ids=google_ids if google_ids or has_explicit_google_id_config(publication) else None,
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
        "google_scholar": {"query": queries["google_scholar"], "citations": google_total, "documents": citation_item_list(google_items)},
        "semantic_scholar": {"query": queries["semantic_scholar"], "citations": semantic_total, "documents": citation_item_list(semantic_items)},
        "ads": {"query": queries["ads"], "citations": ads_total, "documents": citation_item_list(ads_items)},
    }
    return citations, cache, stale_sources


def yaml_indent(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line else line for line in text.splitlines())


def make_citations_block(citations: dict[str, Any]) -> str:
    dumped = yaml.safe_dump(citations, sort_keys=False, allow_unicode=True, width=1000).rstrip()
    return "  citations:\n" + yaml_indent(dumped, 4) + "\n"


def yaml_node_end(node: yaml.Node) -> int:
    if isinstance(node, yaml.MappingNode) and node.value and not node.flow_style:
        return max(yaml_node_end(value) for _, value in node.value)
    if isinstance(node, yaml.SequenceNode) and node.value and not node.flow_style:
        return max(yaml_node_end(value) for value in node.value)
    return node.end_mark.index


def replace_or_insert_citations_block(block_text: str, citations: dict[str, Any]) -> str:
    original = load_yaml_mapping(block_text)
    paper_key = next(iter(original))
    if original[paper_key].get("citations") == citations:
        return block_text
    # YAML source marks handle quoted keys and inline mappings without touching abstract text.
    root = yaml.compose(block_text)
    publication = root.value[0][1]
    start = end = len(block_text)
    for key, value in publication.value:
        if key.value == "citations":
            start = block_text.rfind("\n", 0, key.start_mark.index) + 1
            node_end = yaml_node_end(value)
            if node_end < key.start_mark.index:
                raise ValueError("Citation aliases cannot be rewritten safely")
            end = block_text.find("\n", node_end)
            end = len(block_text) if end == -1 else end + 1
            break
    else:
        for key, _ in publication.value:
            if key.value in {"abstract", "author_marks", "selected", "bibtex_show"}:
                start = end = block_text.rfind("\n", 0, key.start_mark.index) + 1
                break
    prefix = block_text[:start]
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    result = prefix + make_citations_block(citations) + block_text[end:]
    expected = {paper_key: {**original[paper_key], "citations": citations}}
    if load_yaml_mapping(result) != expected:
        raise ValueError(f"{paper_key}: citation edit would alter unrelated publication metadata")
    return result


def update_publications_file(
    path: Path,
    articles_by_title: dict[str, dict[str, Any]] | None,
    serpapi_key: str,
    semantic_scholar_key: str | None,
    ads_token: str,
    allow_decrease: bool = False,
) -> tuple[str, dict[str, dict[str, Any]], UpdateSummary]:
    original = path.read_text(encoding="utf-8")
    blocks = find_publication_blocks(original)
    metadata = bib_metadata_by_key()
    existing_cache_by_paper = load_existing_cited_documents()
    configured_keys = [block.key for block in blocks if publication_has_citation_config(parse_publication(block))]
    summary = UpdateSummary(citation_configured=len(configured_keys))

    log(f"Updating {summary.citation_configured} citation-enabled publication(s).")

    rebuilt_parts: list[str] = []
    cursor = 0
    cache_by_paper: dict[str, dict[str, Any]] = {}

    for block in blocks:
        rebuilt_parts.append(original[cursor:block.start])
        cursor = block.end

        publication = parse_publication(block)
        bib_metadata = metadata.get(block.key)
        if not publication_has_citation_config(publication):
            rebuilt_parts.append(block.text)
            if block.key in existing_cache_by_paper:
                cache_by_paper[block.key] = existing_cache_by_paper[block.key]
            continue

        existing_cache = existing_cache_by_paper.get(block.key, empty_cited_documents_entry())
        cache_by_paper[block.key] = existing_cache

        try:
            citations, cache, stale_sources = generate_publication_citations(
                publication,
                bib_metadata,
                articles_by_title,
                serpapi_key,
                semantic_scholar_key,
                ads_token,
                existing_cache,
                block.key,
                allow_decrease,
            )
            new_block_text = replace_or_insert_citations_block(block.text, citations)
        except (ApiError, ValueError) as error:
            summary.failed += 1
            warn(f"{block.key}: {error}; keeping previous counts and documents.")
            rebuilt_parts.append(block.text)
            continue

        cache_by_paper[block.key] = cache

        block_changed = new_block_text != block.text
        if stale_sources:
            summary.partial += 1
        else:
            summary.updated += 1
        google = citations.get("google_scholar", {})
        semantic = citations.get("semantic_scholar", {})
        ads = citations.get("ads", {})
        state = "changed" if block_changed or cache != existing_cache else "unchanged"
        if stale_sources:
            state += "; cached=" + ",".join(stale_sources)
        old_total = publication.get("citations", {}).get("total", "unknown")
        log(
            f"{block.key}: total={old_total}->{citations.get('total', 0)}; "
            f"google={google.get('citations', 0)} ({len(google.get('ids') or [])} id(s)), "
            f"s2={semantic.get('citations', 0)} (unique +{semantic.get('extra_non_duplicate', 0)}), "
            f"ads={ads.get('citations', 0)} (unique +{ads.get('extra_non_duplicate', 0)}); "
            f"{state}."
        )
        rebuilt_parts.append(new_block_text)

    rebuilt_parts.append(original[cursor:])
    for key, value in existing_cache_by_paper.items():
        cache_by_paper.setdefault(key, value)
    return "".join(rebuilt_parts), cache_by_paper, summary


def write_citation_files(publications: str, cache_by_paper: dict[str, dict[str, Any]]) -> list[Path]:
    outputs = {
        PUBLICATIONS_PATH: publications,
        CITED_DOCUMENTS_PATH: yaml.safe_dump({"papers": cache_by_paper}, sort_keys=False, allow_unicode=True, width=1000),
    }
    staged: dict[Path, Path] = {}
    originals: dict[Path, bytes | None] = {}
    replaced: list[Path] = []
    try:
        # Stage both files before replacing either; roll back ordinary I/O failures below.
        for path, content in outputs.items():
            load_yaml_mapping(content)
            original = path.read_bytes() if path.exists() else None
            if original == content.encode("utf-8"):
                continue
            originals[path] = original
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
                staged[path] = Path(temporary.name)
                temporary.write(content.encode("utf-8"))
            staged[path].chmod(path.stat().st_mode & 0o777 if path.exists() else 0o644)
        for path, temporary in staged.items():
            os.replace(temporary, path)
            replaced.append(path)
    except Exception:
        for path in replaced:
            if originals[path] is None:
                path.unlink()
            else:
                path.write_bytes(originals[path])
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
    return replaced


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-decrease", action="store_true", help="Accept source count decreases after manual review")
    args = parser.parse_args(argv)
    serpapi_key = load_env("SERPAPI_API_KEY")
    ads_token = load_env("ADS_API_TOKEN")
    semantic_scholar_key = load_env("SEMANTIC_SCHOLAR_API_KEY")

    log(
        "API keys: "
        f"SerpApi={'configured' if serpapi_key else 'missing'}, "
        f"ADS={'configured' if ads_token else 'missing'}, "
        f"Semantic Scholar={'configured' if semantic_scholar_key else 'missing (unauthenticated)'}."
    )

    if not serpapi_key:
        warn("SERPAPI_API_KEY is not set; citation update was not run.")
        return 1
    if not ads_token:
        warn("ADS_API_TOKEN is not set; citation update was not run.")
        return 1

    author_lookup_keys = publications_needing_google_author_lookup(PUBLICATIONS_PATH)
    articles_by_title = None

    if author_lookup_keys:
        log(
            "Google Scholar author fallback needed for paper(s) without explicit citation IDs: "
            + ", ".join(author_lookup_keys)
        )
        try:
            scholar_user_id = load_scholar_user_id()
            articles = fetch_google_author_articles(scholar_user_id, serpapi_key)
            articles_by_title = index_articles_by_title(articles)
            log(f"Google Scholar author fallback ready: fetched {len(articles)} author article(s).")
        except Exception as error:
            articles_by_title = None
            warn(f"Failed to fetch Scholar author data; title fallback is disabled for this run: {error}")
    else:
        log("Google Scholar author fallback skipped: Google citation ID config is explicit for all citation-enabled papers.")

    publications, cache_by_paper, summary = update_publications_file(
        PUBLICATIONS_PATH,
        articles_by_title,
        serpapi_key,
        semantic_scholar_key,
        ads_token,
        args.allow_decrease,
    )
    changed_paths = write_citation_files(publications, cache_by_paper)

    log(
        f"Summary: refreshed={summary.updated}/{summary.citation_configured}, "
        f"partial={summary.partial}, failed={summary.failed}; "
        f"changed files: {', '.join(str(path) for path in changed_paths) or 'none'}."
    )
    return 1 if summary.failed or summary.partial else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        warn(f"Citation update aborted: {type(error).__name__}: {error}")
        raise SystemExit(1) from None
