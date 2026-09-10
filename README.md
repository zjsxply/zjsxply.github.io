# Linyue Pan Personal Website

This is Linyue Pan's personal academic website based on [al-folio](https://github.com/alshedivat/al-folio).

## Domain

The site is configured as a GitHub Pages user site:

```yaml
url: https://zjsxply.github.io
baseurl:
```

The repository should be named `zjsxply.github.io`. The deployment workflow builds the site from `main` and publishes the generated `_site` directory to the `gh-pages` branch.

## Citation Updates

`.github/workflows/update-scholar-citations.yml` runs Mondays at 08:00 Beijing time, updating `_data/publications.yml` and `_data/publication_cited_documents.yml` from Google Scholar, Semantic Scholar, and ADS.

- Numeric `citations.google_scholar.ids` are queried independently, excluding patents and disabling similar-result filtering, then following the returned next-page context. Explicit `ids: []` disables author lookup; unresolved automatic discovery remains retryable without writing `ids: []`.
- Deduplication uses stable IDs or exact normalized titles, rejects conflicting arXiv/DOI IDs, and never uses fuzzy matches. Cached source `citations` is the unique count; `documents` preserves evidence variants with arXiv/DOI and title-alias metadata, so its length is not a citation count. Source `query` metadata rejects fallback caches for changed query IDs.
- Failed sources reuse valid caches while healthy sources refresh; without a usable fallback, the paper is preserved. Decreases retain cached data unless reconciliation covers every historical work. Use `--allow-decrease` only for manually reviewed real declines.
- Exit `0` means full success; partial updates, failures, or missing required keys return `1`. The workflow commits and deploys available healthy updates before marking an incomplete run red.

Required secrets: `SERPAPI_API_KEY` and `ADS_API_TOKEN`; optional: `SEMANTIC_SCHOLAR_API_KEY`. Locally, use the existing uv environment and untracked `.env` from the repository root; never commit secret values:

```bash
source .venv/bin/activate
uv pip install pyyaml
set -a
source .env
set +a
python bin/update_scholar_citations_serpapi.py
```

## Local Preview

```bash
cd /home/panly/personal-homepage
docker compose pull
docker compose up
```

Then open <http://localhost:8080>.
