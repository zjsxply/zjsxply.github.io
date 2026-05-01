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
        },{id: "news-released-natural-language-agent-harnesses-a-prototype-for-next-generation-agent-systems",
          title: '🚀 Released Natural-Language Agent Harnesses, a prototype for next-generation agent systems.',
          description: "",
          section: "News",},{id: "news-发布-natural-language-agent-harnesses-探索下一代-agent-系统原型",
          title: '🚀 发布 Natural-Language Agent Harnesses，探索下一代 Agent 系统原型。',
          description: "",
          section: "News",},{id: "news-nlah-reached-alphaxiv-hot-1-and-received-550k-views-on-x",
          title: '🔥 NLAH reached alphaXiv Hot #1 and received 550K+ views on X.',
          description: "",
          section: "News",},{id: "news-nlah-登顶-alphaxiv-热榜第一-并在-x-上获得-55-万-浏览",
          title: '🔥 NLAH 登顶 alphaXiv 热榜第一，并在 X 上获得 55 万+浏览。',
          description: "",
          section: "News",},{id: "news-nlah-featured-in-dair-ai-s-weekly-top-10-papers",
          title: '🎉 NLAH featured in DAIR.AI’s Weekly Top 10 Papers!',
          description: "",
          section: "News",},{id: "news-nlah-入选-dair-ai-每周十佳论文",
          title: '🎉 NLAH 入选 DAIR.AI 每周十佳论文！',
          description: "",
          section: "News",},{id: "news-catarena-accepted-at-icml-2026",
          title: '🎉 CATArena accepted at ICML 2026!',
          description: "",
          section: "News",},{id: "news-catarena-被-icml-2026-接收",
          title: '🎉 CATArena 被 ICML 2026 接收！',
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
