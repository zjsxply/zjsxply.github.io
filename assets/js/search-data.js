// get the ninja-keys element
const ninja = document.querySelector('ninja-keys');

// add the home and posts menu items
ninja.data = [{
    id: "nav-about",
    title: "about",
    section: "Navigation",
    handler: () => {
      window.location.href = "/panly.github.io/";
    },
  },{id: "nav-publications",
          title: "publications",
          description: "Preprints and manuscripts on AI agents, agent harnesses, coding agents, and evaluation.",
          section: "Navigation",
          handler: () => {
            window.location.href = "/panly.github.io/publications/";
          },
        },{id: "nav-code",
          title: "code",
          description: "Selected GitHub repositories and open-source work.",
          section: "Navigation",
          handler: () => {
            window.location.href = "/panly.github.io/repositories/";
          },
        },{id: "news-️-super-excited-to-launch-catarena-we-built-a-tournament-style-benchmark-to-push-a-much-tougher-question-for-coding-agents-can-they-actually-get-stronger-through-iterative-feedback-self-reflection-and-peer-experience",
          title: '⚔️ Super excited to launch CATArena! We built a tournament-style benchmark to push...',
          description: "",
          section: "News",},{id: "news-thrilled-to-share-our-academic-prototype-natural-language-agent-harnesses-we-believe-nlah-points-to-a-possible-next-generation-paradigm-for-agent-systems-such-as-claude-code-and-openclaw-moving-harness-logic-from-hard-coded-controllers-into-executable-natural-language",
          title: '🚀 Thrilled to share our academic prototype, Natural-Language Agent Harnesses! We believe NLAH...',
          description: "",
          section: "News",},{id: "news-what-an-unbelievable-week-for-nlah-it-was-reposted-by-a-deepmind-researcher-and-the-chief-scientist-of-hugging-face-surged-to-alphaxiv-hot-1-and-was-selected-by-the-ai-timeline-as-one-of-only-seven-top-ai-ml-research-papers-of-the-week",
          title: '🔥 What an unbelievable week for NLAH! It was reposted by a DeepMind...',
          description: "",
          section: "News",},{id: "news-amazing-news-nlah-was-featured-in-dair-ai-s-weekly-top-10-papers-really-grateful-and-energized-to-see-natural-language-harnesses-resonate-with-the-broader-agent-community",
          title: '🎉 Amazing news: NLAH was featured in DAIR.AI’s Weekly Top 10 Papers! Really...',
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
