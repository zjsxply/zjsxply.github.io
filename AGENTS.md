# Agent Guidelines for al-folio

A simple, clean, and responsive Jekyll theme for academics.

## Quick Links by Role

- **Are you a coding agent?** → Read [`.github/copilot-instructions.md`](.github/copilot-instructions.md) first (tech stack, build, CI/CD, common pitfalls & solutions)
- **Customizing the site?** → See [`.github/agents/customize.agent.md`](.github/agents/customize.agent.md)
- **Writing documentation?** → See [`.github/agents/docs.agent.md`](.github/agents/docs.agent.md)
- **Need setup/deployment help?** → [INSTALL.md](INSTALL.md)
- **Troubleshooting & FAQ?** → [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Customization & theming?** → [CUSTOMIZE.md](CUSTOMIZE.md)
- **Quick 5-min start?** → [QUICKSTART.md](QUICKSTART.md)

## Essential Commands

### Local Development (Docker)

The recommended approach is using Docker.

```bash
# Initial setup & start dev server
docker compose pull && docker compose up
# Site runs at http://localhost:8080

# Rebuild after changing dependencies or Dockerfile
docker compose up --build

# Stop containers and free port 8080
docker compose down
```

### Pre-Commit Checklist

Before every commit, you **must** run these steps:

1.  **Format Code:**
    ```bash
    # (First time only)
    npm install --save-dev prettier @shopify/prettier-plugin-liquid
    # Format all files
    npx prettier . --write
    ```
2.  **Build Locally & Verify:**

    ```bash
    # Rebuild the site
    docker compose up --build

    # Verify by visiting http://localhost:8080.
    # Check navigation, pages, images, and dark mode.
    ```

## Critical Configuration

When modifying `_config.yml`, these **must be updated together**:

- **Personal site:** `url: https://username.github.io` + `baseurl:` (empty)
- **Project site:** `url: https://username.github.io` + `baseurl: /repo-name/`
- **YAML errors:** Quote strings with special characters: `title: "My: Cool Site"`

## Development Workflow

- **Git & Commits:** For commit message format and Git practices, see [.github/GIT_WORKFLOW.md](.github/GIT_WORKFLOW.md).
- **Code-Specific Instructions:** Consult the relevant instruction file for your code type.

| File Type                                     | Instruction File                                                                                |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Markdown content (`_posts/`, `_pages/`, etc.) | [markdown-content.instructions.md](.github/instructions/markdown-content.instructions.md)       |
| YAML config (`_config.yml`, `_data/`)         | [yaml-configuration.instructions.md](.github/instructions/yaml-configuration.instructions.md)   |
| BibTeX (`_bibliography/`)                     | [bibtex-bibliography.instructions.md](.github/instructions/bibtex-bibliography.instructions.md) |
| Liquid templates (`_includes/`, `_layouts/`)  | [liquid-templates.instructions.md](.github/instructions/liquid-templates.instructions.md)       |
| JavaScript (`_scripts/`)                      | [javascript-scripts.instructions.md](.github/instructions/javascript-scripts.instructions.md)   |

## Common Issues

For troubleshooting, see:

- [Common Pitfalls & Workarounds](.github/copilot-instructions.md#common-pitfalls--workarounds) in copilot-instructions.md
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for detailed solutions
- [GitHub Issues](https://github.com/alshedivat/al-folio/issues) to search for your specific problem.

## Owner Requirement Summary

This section summarizes the site owner's main requirements from the homepage-building session. Keep it concise and use it as preference guidance when making future changes.

### Core Direction

- Build and maintain a polished academic homepage based on al-folio for `https://zjsxply.github.io/`.
- Keep the style clean, mature, and academic, while allowing energetic news wording and tasteful emoji.
- Prefer Docker-based local builds and Prettier formatting before commits.
- Do not commit, push, revert, or force-push unless the user explicitly asks; if undoing commits, prefer direct history edits over revert commits when requested.
- Never expose or commit credentials, tokens, `.git-credentials`, `auth.json`, or secret values.

### Site Structure

- English is the default site; Chinese lives under `/zh/` with browser-language auto-detection and manual language switching.
- Use consistent bilingual filenames such as `name.zh.md` and `name.zh.yml`.
- Keep CV/PDF hidden and keep Projects removed; use the code/repositories page instead.
- Keep footer and UI text localized, but do not add verbose footer contact text.

### Homepage Content

- Name format: English `Linyue Pan (潘林越)`; Chinese `潘林越 (Linyue Pan)`.

### Contacts

- Primary email is `ply24@mails.tsinghua.edu.cn`; WeChat ID is `fallendown759`.
- WeChat should open a localized modal and support click-to-copy from both the ID area and the “Click to copy / 点击复制” hint.
- Visible contact icons should emphasize mail, X, WeChat, LinkedIn, Google Scholar, GitHub, DBLP, and ORCID; avoid showing OpenReview/AMiner icons unless their appearance is improved.

### Bilingual Writing Preferences

- Do not translate `harness`; translate NLAH as `自然语言的 Agent Harness`.
- Chinese wording preferences include `郑海涛副教授`, `自我进化`, `经营模拟`, and `LongCat 基础模型团队`.
- Chinese locations should avoid country names; use city names such as `北京`, `深圳`, and `徐州`.
- Chinese publication UI labels, footer text, WeChat copy text, news text, abstracts, notes, and section titles should be localized.
- Avoid forcing `&hl=en` in links.

### Publications And Metrics

- `_bibliography/papers.bib` must contain only arXiv-exported BibTeX data; all website-specific metadata belongs in `_data/publications.yml` or `_data/publications.zh.yml`.
- Preserve exact arXiv author lists and never use `others`.
- Do not show `HTML` buttons for the current papers.
- Google Scholar citations should be updated by the SerpAPI GitHub Action into `_data/publications.yml`; do not write citation counts into BibTeX. GitHub stars may be shown separately.

### Chinese Publication Authors

- Use Chinese real names where known.
- Preserve author profile links in both languages when available.

### News, Experience, Education, Honors

- Homepage news should show five items and use an excited, celebratory tone.
