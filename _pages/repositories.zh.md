---
layout: page
permalink: /zh/repositories/
lang: zh
lang_ref: repositories
en_url: /repositories/
title: 代码
description: 代表性的 GitHub 仓库与开源工作。
nav: true
nav_order: 2
---

{% if site.data.repositories.github_users %}

## GitHub 主页

<div class="repositories d-flex flex-wrap flex-md-row flex-column justify-content-between align-items-center">
  {% for user in site.data.repositories.github_users %}
    {% include repository/repo_user.liquid username=user %}
  {% endfor %}
</div>

---

{% endif %}

{% if site.data.repositories.github_repos %}

## 代表性仓库

<div class="repositories d-flex flex-wrap flex-md-row flex-column justify-content-between align-items-center">
  {% for repo in site.data.repositories.github_repos %}
    {% include repository/repo.liquid repository=repo %}
  {% endfor %}
</div>

{% endif %}
