// get the ninja-keys element
const ninja = document.querySelector('ninja-keys');

// add the home and posts menu items
ninja.data = [{
    id: "nav-about",
    title: "about",
    section: "Navigation",
    handler: () => {
      window.location.href = "/";
    },
  },{id: "nav-publications",
          title: "publications",
          description: "Preprints and manuscripts on AI agents, agent harnesses, coding agents, and evaluation.",
          section: "Navigation",
          handler: () => {
            window.location.href = "/publications/";
          },
        },{id: "nav-论文",
          title: "论文",
          description: "关于 AI Agents、Agent Harnesses、Coding Agents 与评测的预印本和论文。",
          section: "Navigation",
          handler: () => {
            window.location.href = "/zh/publications/";
          },
        },{id: "nav-code",
          title: "code",
          description: "Selected GitHub repositories and open-source work.",
          section: "Navigation",
          handler: () => {
            window.location.href = "/repositories/";
          },
        },{id: "nav-代码",
          title: "代码",
          description: "代表性的 GitHub 仓库与开源工作。",
          section: "Navigation",
          handler: () => {
            window.location.href = "/zh/repositories/";
          },
        },{id: "news-️-super-excited-to-launch-catarena-we-built-a-tournament-style-benchmark-to-push-a-much-tougher-question-for-coding-agents-can-they-actually-get-stronger-through-iterative-feedback-self-reflection-and-peer-experience",
          title: '⚔️ Super excited to launch CATArena! We built a tournament-style benchmark to push...',
          description: "",
          section: "News",},{id: "news-️-很激动发布-catarena-我们构建了一个锦标赛式-benchmark-想追问一个更难也更真实的问题-coding-agents-能否真的通过迭代反馈-自我反思和同伴经验变得更强",
          title: '⚔️ 很激动发布 CATArena！我们构建了一个锦标赛式 benchmark，想追问一个更难也更真实的问题：Coding Agents 能否真的通过迭代反馈、自我反思和同伴经验变得更强？',
          description: "",
          section: "News",},{id: "news-thrilled-to-share-our-academic-prototype-natural-language-agent-harnesses-we-believe-nlah-points-to-a-possible-next-generation-paradigm-for-agent-systems-such-as-claude-code-and-openclaw-moving-harness-logic-from-hard-coded-controllers-into-executable-natural-language",
          title: '🚀 Thrilled to share our academic prototype, Natural-Language Agent Harnesses! We believe NLAH...',
          description: "",
          section: "News",},{id: "news-很高兴分享我们的学术原型-natural-language-agent-harnesses-我们相信-nlah-可能指向-claude-code-openclaw-等-agent-系统的下一代范式-把-harness-逻辑从硬编码控制器迁移到可执行的自然语言中",
          title: '🚀 很高兴分享我们的学术原型 Natural-Language Agent Harnesses！我们相信 NLAH 可能指向 Claude Code、OpenClaw 等 Agent 系统的下一代范式：把 harness...',
          description: "",
          section: "News",},{id: "news-what-an-unbelievable-week-for-nlah-it-was-reposted-by-a-deepmind-researcher-and-the-chief-scientist-of-hugging-face-surged-to-alphaxiv-hot-1-and-was-selected-by-the-ai-timeline-as-one-of-only-seven-top-ai-ml-research-papers-of-the-week",
          title: '🔥 What an unbelievable week for NLAH! It was reposted by a DeepMind...',
          description: "",
          section: "News",},{id: "news-对-nlah-来说-这是令人难以置信的一周-论文被-deepmind-研究员和-hugging-face-首席科学家转发-冲上-alphaxiv-hot-1-并被-the-ai-timeline-选为当周仅-7-篇-top-ai-ml-研究论文之一",
          title: '🔥 对 NLAH 来说，这是令人难以置信的一周！论文被 DeepMind 研究员和 Hugging Face 首席科学家转发，冲上 alphaXiv Hot #1，并被 The...',
          description: "",
          section: "News",},{id: "news-amazing-news-nlah-was-featured-in-dair-ai-s-weekly-top-10-papers-really-grateful-and-energized-to-see-natural-language-harnesses-resonate-with-the-broader-agent-community",
          title: '🎉 Amazing news: NLAH was featured in DAIR.AI’s Weekly Top 10 Papers! Really...',
          description: "",
          section: "News",},{id: "news-太开心了-nlah-入选-dair-ai-weekly-top-10-papers-非常感谢社区对-natural-language-harnesses-方向的关注和讨论",
          title: '🎉 太开心了：NLAH 入选 DAIR.AI Weekly Top 10 Papers！非常感谢社区对 Natural-Language Harnesses 方向的关注和讨论。',
          description: "",
          section: "News",},{id: "news-excited-to-share-that-catarena-has-been-accepted-to-icml-2026-grateful-to-the-team-and-looking-forward-to-sharing-more-about-evaluating-the-evolutionary-capacity-of-coding-agents",
          title: '🎉 Excited to share that CATArena has been accepted to ICML 2026! Grateful...',
          description: "",
          section: "News",},{id: "news-很开心-catarena-被-icml-2026-接收-感谢团队所有伙伴-也期待继续和大家交流-coding-agent-进化能力评测这个方向",
          title: '🎉 很开心，CATArena 被 ICML 2026 接收！感谢团队所有伙伴，也期待继续和大家交流 Coding Agent 进化能力评测这个方向。',
          description: "",
          section: "News",},{
        id: 'social-email',
        title: 'email',
        section: 'Socials',
        handler: () => {
          window.open("mailto:%70%6C%79%32%34@%6D%61%69%6C%73.%74%73%69%6E%67%68%75%61.%65%64%75.%63%6E", "_blank");
        },
      },{
        id: 'social-x',
        title: 'X',
        section: 'Socials',
        handler: () => {
          window.open("https://twitter.com/ply_thu", "_blank");
        },
      },{
        id: 'social-wechat',
        title: 'Wechat',
        section: 'Socials',
        handler: () => {
          window.open("#wechat", "_blank");
        },
      },{
        id: 'social-linkedin',
        title: 'LinkedIn',
        section: 'Socials',
        handler: () => {
          window.open("https://www.linkedin.com/in/linyue-pan", "_blank");
        },
      },{
        id: 'social-scholar',
        title: 'Google Scholar',
        section: 'Socials',
        handler: () => {
          window.open("https://scholar.google.com/citations?user=xS16saYAAAAJ", "_blank");
        },
      },{
        id: 'social-github',
        title: 'GitHub',
        section: 'Socials',
        handler: () => {
          window.open("https://github.com/zjsxply", "_blank");
        },
      },{
        id: 'social-dblp',
        title: 'DBLP',
        section: 'Socials',
        handler: () => {
          window.open("https://dblp.org/pid/427/5268", "_blank");
        },
      },{
        id: 'social-orcid',
        title: 'ORCID',
        section: 'Socials',
        handler: () => {
          window.open("https://orcid.org/0009-0003-8048-5553", "_blank");
        },
      },{
      id: 'light-theme',
      title: 'Change theme to light',
      description: 'Change the theme of the site to Light',
      section: 'Theme',
      handler: () => {
        setThemeSetting("light");
      },
    },
    {
      id: 'dark-theme',
      title: 'Change theme to dark',
      description: 'Change the theme of the site to Dark',
      section: 'Theme',
      handler: () => {
        setThemeSetting("dark");
      },
    },
    {
      id: 'system-theme',
      title: 'Use system default theme',
      description: 'Change the theme of the site to System Default',
      section: 'Theme',
      handler: () => {
        setThemeSetting("system");
      },
    },];
