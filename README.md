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

Citation badges are updated weekly by `.github/workflows/update-scholar-citations.yml`.
The workflow uses SerpApi for Google Scholar and the Semantic Scholar Graph API, then deduplicates citing papers across both sources before updating `_data/publications.yml`.
HTTP 429 responses are retried once per second up to 120 times.
If either source still fails for a publication, that publication keeps its previous citation values for the run.
Use `scholar_citation_ids` for the numeric `cites` IDs from Google Scholar "Cited by" URLs.
If Google Scholar splits one paper across records, include all numeric `cites` IDs; the workflow will query the combined Cited by URL.
Entries without `scholar_citation_ids` fall back to normalized title matching against `_bibliography/papers.bib`.
Semantic Scholar is matched by `semantic_scholar_paper_id`, or by BibTeX arXiv/DOI metadata when that field is missing.

To enable it, add a repository secret named `SERPAPI_API_KEY` in GitHub Actions secrets.
Optionally add `SEMANTIC_SCHOLAR_API_KEY` to reduce Semantic Scholar rate limits.
Without `SERPAPI_API_KEY`, the workflow exits successfully and leaves citation counts unchanged.

## Local Preview

```bash
cd /home/panly/personal-homepage
docker compose pull
docker compose up
```

Then open <http://localhost:8080>.
