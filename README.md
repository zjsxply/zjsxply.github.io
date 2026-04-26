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

Google Scholar citation badges are updated weekly by `.github/workflows/update-scholar-citations.yml`.
The workflow uses SerpApi's Google Scholar Author API and updates only BibTeX entries that already contain `scholar_citations`.

To enable it, add a repository secret named `SERPAPI_API_KEY` in GitHub Actions secrets.
Without this secret, the workflow exits successfully and leaves citation counts unchanged.

## Local Preview

```bash
cd /home/panly/personal-homepage
docker compose pull
docker compose up
```

Then open <http://localhost:8080>.
