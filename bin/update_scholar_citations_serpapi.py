#!/usr/bin/env python3
"""Update manual Scholar citation badges in _data/publications.yml via SerpApi.

The script updates only publication config entries that contain a
scholar_citations field. If scholar_citation_id is present, it is matched
against the Google Scholar "cites" ID from the Cited by URL:

    https://scholar.google.com/scholar?cites=<scholar_citation_id>

If Scholar splits one paper across records, scholar_citation_ids may list
multiple cites IDs. The script then queries the combined Cited by search:

    https://scholar.google.com/scholar?cites=<id_1>,<id_2>

Entries without scholar_citation_id or scholar_citation_ids fall back to exact
normalized title matching against the corresponding BibTeX title.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

BIB_PATH = Path("_bibliography/papers.bib")
PUBLICATIONS_PATH = Path("_data/publications.yml")
SOCIALS_PATH = Path("_data/socials.yml")
SERPAPI_URL = "https://serpapi.com/search.json"


@dataclass(frozen=True)
class BibEntry:
    key: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class PublicationBlock:
    key: str
    start: int
    end: int
    text: str


def load_scholar_user_id() -> str:
    if not SOCIALS_PATH.exists():
        raise FileNotFoundError(f"Missing {SOCIALS_PATH}")

    for line in SOCIALS_PATH.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*scholar_userid\s*:\s*([^#\s]+)", line)
        if match:
            return match.group(1).strip().strip('"\'')

    raise ValueError(f"Could not find scholar_userid in {SOCIALS_PATH}")


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

    single_id = extract_yaml_scalar(block_text, "scholar_citation_id")
    if single_id:
        citation_ids.extend(split_scholar_citation_ids(single_id))

    normalized_ids: list[str] = []
    seen: set[str] = set()
    for citation_id in citation_ids:
        if not re.fullmatch(r"\d+", citation_id):
            raise ValueError(f"Invalid Scholar cites ID: {citation_id}")
        if citation_id not in seen:
            normalized_ids.append(citation_id)
            seen.add(citation_id)

    return normalized_ids


def normalize_title(title: str) -> str:
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


def update_yaml_citation_field(block_text: str, citations: int) -> str:
    citation_pattern = re.compile(r"(?m)^(\s{2}scholar_citations:\s*).*$")
    updated, count = citation_pattern.subn(rf"\g<1>{citations}", block_text, count=1)
    if count != 1:
        raise ValueError("Publication was selected for update but scholar_citations field was not found")
    return updated


def fetch_serpapi_articles(author_id: str, api_key: str) -> list[dict]:
    articles: list[dict] = []
    start = 0
    page_size = 100

    while True:
        params = {
            "engine": "google_scholar_author",
            "author_id": author_id,
            "hl": "en",
            "num": str(page_size),
            "start": str(start),
            "api_key": api_key,
        }
        url = f"{SERPAPI_URL}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if "error" in payload:
            raise RuntimeError(f"SerpApi error: {payload['error']}")

        page_articles = payload.get("articles") or []
        articles.extend(page_articles)

        if len(page_articles) < page_size:
            break
        start += page_size
        if start >= 500:
            raise RuntimeError("Refusing to fetch more than 500 Scholar articles")

    return articles


def fetch_serpapi_combined_citation_count(citation_ids: list[str], api_key: str) -> int:
    params = {
        "engine": "google_scholar",
        "cites": ",".join(citation_ids),
        "hl": "en",
        "num": "1",
        "api_key": api_key,
    }
    url = f"{SERPAPI_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if "error" in payload:
        raise RuntimeError(f"SerpApi error: {payload['error']}")

    search_information = payload.get("search_information")
    if not isinstance(search_information, dict):
        raise RuntimeError(f"SerpApi response for cites={','.join(citation_ids)} has no search_information")

    total_results = search_information.get("total_results")
    if isinstance(total_results, int):
        return total_results
    if isinstance(total_results, str) and total_results.isdigit():
        return int(total_results)

    raise RuntimeError(f"SerpApi response for cites={','.join(citation_ids)} has no total_results")


def article_citations(article: dict) -> int | None:
    cited_by = article.get("cited_by")
    if isinstance(cited_by, dict):
        value = cited_by.get("value")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


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


def index_articles_by_scholar_citation_id(articles: list[dict]) -> dict[str, dict]:
    by_scholar_citation_id: dict[str, dict] = {}

    for article in articles:
        scholar_citation_id = article_scholar_citation_id(article)
        if not scholar_citation_id:
            continue
        if scholar_citation_id in by_scholar_citation_id:
            raise ValueError(f"Duplicate SerpApi article with cites={scholar_citation_id}")
        by_scholar_citation_id[scholar_citation_id] = article

    return by_scholar_citation_id


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


def bib_titles_by_key() -> dict[str, str]:
    original = BIB_PATH.read_text(encoding="utf-8")
    entries = find_bib_entries(original)
    titles: dict[str, str] = {}
    for entry in entries:
        title = extract_field(entry.text, "title")
        if title:
            titles[entry.key] = title
    return titles


def update_publication_data(articles: list[dict], api_key: str) -> bool:
    original = PUBLICATIONS_PATH.read_text(encoding="utf-8")
    blocks = find_publication_blocks(original)
    titles = bib_titles_by_key()
    by_scholar_citation_id = index_articles_by_scholar_citation_id(articles)
    by_title = index_articles_by_title(articles)

    rebuilt_parts: list[str] = []
    cursor = 0
    changed = False
    errors: list[str] = []

    for block in blocks:
        rebuilt_parts.append(original[cursor:block.start])
        block_text = block.text
        cursor = block.end

        if extract_yaml_scalar(block_text, "scholar_citations") is None:
            rebuilt_parts.append(block_text)
            continue

        scholar_citation_ids = extract_scholar_citation_ids(block_text)
        if scholar_citation_ids:
            if len(scholar_citation_ids) > 1:
                try:
                    citations = fetch_serpapi_combined_citation_count(scholar_citation_ids, api_key)
                except Exception as error:
                    errors.append(f"{block.key}: failed combined cites lookup: {error}")
                    rebuilt_parts.append(block_text)
                    continue

                old_citations = extract_yaml_scalar(block_text, "scholar_citations")
                print(f"{block.key}: {old_citations} -> {citations} (cites={','.join(scholar_citation_ids)})")
                new_block_text = update_yaml_citation_field(block_text, citations)
                if new_block_text != block_text:
                    changed = True
                rebuilt_parts.append(new_block_text)
                continue

            scholar_citation_id = scholar_citation_ids[0]
            article = by_scholar_citation_id.get(scholar_citation_id)
            if article is None:
                errors.append(f"{block.key}: no SerpApi article matched cites={scholar_citation_id}")
                rebuilt_parts.append(block_text)
                continue
        else:
            title = titles.get(block.key)
            if not title:
                errors.append(f"{block.key}: missing BibTeX title for title fallback")
                rebuilt_parts.append(block_text)
                continue

            article = by_title.get(normalize_title(title))
            if article is None:
                errors.append(f"{block.key}: no SerpApi article matched title fallback: {title}")
                rebuilt_parts.append(block_text)
                continue

        citations = article_citations(article)
        if citations is None:
            errors.append(f"{block.key}: matched SerpApi article has no citation count")
            rebuilt_parts.append(block_text)
            continue

        old_citations = extract_yaml_scalar(block_text, "scholar_citations")
        title = article.get("title") or block.key
        print(f"{title}: {old_citations} -> {citations}")
        new_block_text = update_yaml_citation_field(block_text, citations)
        if new_block_text != block_text:
            changed = True
        rebuilt_parts.append(new_block_text)

    rebuilt_parts.append(original[cursor:])
    if errors:
        raise RuntimeError("Scholar citation update failed:\n- " + "\n- ".join(errors))

    updated = "".join(rebuilt_parts)
    if changed:
        PUBLICATIONS_PATH.write_text(updated, encoding="utf-8")
    return changed


def main() -> int:
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        print("SERPAPI_API_KEY is not set; skipping Scholar citation update.")
        return 0

    author_id = os.environ.get("GOOGLE_SCHOLAR_ID") or load_scholar_user_id()
    print(f"Fetching Google Scholar author data for {author_id} via SerpApi")
    articles = fetch_serpapi_articles(author_id, api_key)
    print(f"Fetched {len(articles)} Scholar articles")

    changed = update_publication_data(articles, api_key)
    print("Updated citation counts." if changed else "Citation counts already up to date.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
