const state = {
  lang: localStorage.getItem("ndo-lang") || "pt",
  route: "home",
  data: null,
  slide: 0,
  timer: null,
  selectedDate: "",
  calendarYear: new Date().getFullYear(),
  calendarMonth: new Date().getMonth() + 1,
  calendarSource: "",
  calendarPickerVisible: null,
  calendarRecommendations: [],
  calendarLoading: false,
  calendarError: "",
  calendarRequest: null,
  dynamicNews: {},
  newsRequestId: "",
  counterFrame: null,
  counterRun: 0,
  topicQuery: "",
  topicSource: "",
  topicAnalyses: [],
  topicResultSets: [],
  topicShowValues: true,
  topicFromDate: "",
  topicToDate: "",
  topicTotal: 0,
  topicSeries: [],
  topicLoading: false,
  topicAbort: null,
  apiBaseUrl: "",
};

const ROUTE_SEGMENTS = new Set(["inicio", "calendário", "calendario", "temas", "documentação", "documentacao", "noticia"]);
const SOURCE_LABELS = {
  "publico.pt": "Público",
  "expresso.pt": "Expresso",
  "cmjornal.pt": "Correio da Manhã",
  "sabado.pt": "Sábado",
  "rtp.pt": "RTP",
  "observador.pt": "Observador",
  "jn.pt": "Jornal de Notícias",
  "dn.pt": "Diário de Notícias",
  "sicnoticias.pt": "SIC Notícias",
  "noticiasaominuto.com": "Notícias ao Minuto",
  "record.pt": "Record",
  "ojogo.pt": "O Jogo",
  "abola.pt": "A Bola",
  "caras.pt": "Caras",
  "flash.pt": "Flash",
  "tv7dias.pt": "TV 7 Dias",
  "holofote.pt": "Holofote",
  "selfie.iol.pt": "Selfie",
  "lux.iol.pt": "Lux",
  "nit.pt": "NiT",
  "timeout.pt": "Time Out",
  "blitz.pt": "Blitz",
  "mag.sapo.pt": "SAPO Mag",
  "visao.pt": "Visão",
  "exameinformatica.pt": "Exame Informática",
  "activa.pt": "Activa",
  "maxima.pt": "Máxima",
};

const i18n = {
  pt: {
    navHome: "Início",
    navCalendar: "Calendário",
    navTopics: "Temas",
    navDocs: "Documentação",
    heroEyebrow: "Notícia principal",
    carouselEyebrow: "Seleção editorial",
    carouselTitle: "Histórias em destaque",
    latestEyebrow: "Arquivo social",
    latestTitle: "Últimas notícias publicadas",
    latestPreviewNote: "Ainda sem posts marcados como publicados; mostramos a fila preparada para revisão.",
    latestPublishedNote: "Atualiza automaticamente quando o publisher marca um post como publicado.",
    openInstagram: "Ver no Instagram",
    openArquivo: "Abrir no Arquivo.pt",
    unavailableInstagram: "Instagram por atualizar",
    unavailableSource: "Fonte por atualizar",
    watermark: "Dados recolhidos via Arquivo.pt",
    originalYear: "Originalmente em",
    scheduledFor: "Preparado para",
    yearOnly: "em",
    calendarEyebrow: "Calendário editorial",
    calendarTitle: "Explorar por data",
    calendarLead: "Escolhe uma data e descobre notícias preservadas para esse dia ao longo dos anos.",
    calendarMonthLabel: "Mês",
    calendarYearLabel: "Ano",
    calendarDateLabel: "Escolher data",
    calendarSourceLabel: "Recomendações de",
    calendarAllSources: "Todos os jornais",
    calendarPreviousDay: "Dia anterior",
    calendarNextDay: "Dia seguinte",
    calendarLoading: "A carregar notícias deste dia...",
    calendarLoadError: "Não foi possível carregar as recomendações deste dia.",
    calendarNoResults: "Não foram encontradas notícias para esta data e fonte.",
    dayRecommendationsTitle: "Notícias importantes deste dia:",
    openDay: "Abrir dia",
    topicsEyebrow: "Pesquisa histórica",
    topicsTitle: "Evolução de um tema",
    topicsLead: "Compara a presença de um tema no índice preservado ao longo dos anos e filtra por fonte.",
    topicLabel: "Tema",
    topicSourceLabel: "Fonte",
    topicColorLabel: "Cor",
    topicShowValues: "Mostrar valores",
    topicAddAnalysis: "Adicionar análise",
    topicRemoveAnalysis: "Remover análise",
    topicComparisonTitle: "Comparação de temas",
    topicFromLabel: "De",
    topicToLabel: "Até",
    topicSubmit: "Analisar",
    topicAllSources: "Todas as fontes",
    topicApiCredit: "Contagem verificada nos resultados indexados pelo Arquivo.pt.",
    topicLoadingNote: "Pode demorar devido ao grande volume de conteúdos analisados. Para pesquisas muito amplas, escolhe uma fonte ou reduz o intervalo.",
    topicCoverageUneven: "A cobertura da pesquisa varia conforme o ano e a fonte; zero significa que o índice não devolveu resultados nesse período.",
    topicLogScale: "Escala logarítmica para tornar visíveis anos com menos resultados.",
    topicCaptureNote: "Cada valor conta registos arquivados que correspondem à pesquisa. A mesma página pode ter sido arquivada mais de uma vez.",
    topicMentions: "resultados verificados",
    topicInstagramLegend: "Publicação no Instagram",
    topicDownload: "Descarregar gráfico",
    topicDownloadFormat: "Formato de descarga",
    topicEmpty: "Não foram encontrados resultados neste intervalo.",
    topicError: "Não foi possível concluir a pesquisa no Arquivo.pt. Tenta novamente dentro de momentos.",
    newsEyebrow: "Notícia preservada",
    newsOpenArquivo: "Abrir notícia no Arquivo.pt",
    newsOpenInstagram: "Abrir publicação no Instagram",
    newsNotFound: "Notícia não encontrada",
    newsNotFoundBody: "Este endereço já não corresponde a uma notícia disponível.",
    newsBack: "Voltar ao calendário",
    docsEyebrow: "Documentação",
    docsTitle: "Como funciona o projeto",
    docsLead: "Notícias de Ontem devolve ao presente histórias preservadas na web e ajuda a percorrer a memória noticiosa por data e por tema.",
    metricsEyebrow: "Cobertura do projeto",
    metricsTitle: "O projeto em números",
    metricNews: "Notícias cobertas",
    metricNewsNote: "Notícias encontradas e organizadas pelo projeto. O total cresce com a recolha.",
    metricPublished: "Publicações feitas",
    metricPublishedNote: "Posts já publicados pelas contas do projeto.",
    metricFollowers: "Seguidores",
    metricFollowersNote: "Soma dos seguidores em todas as redes sociais do projeto.",
    metricYears: "Anos cobertos",
    metricSources: "Fontes acompanhadas",
    docsGithubTitle: "Código e documentação técnica",
    docsGithubBody: "Consulta no GitHub a metodologia completa, os dados e as instruções para executar o projeto.",
    footerCredit: "Dados recolhidos e contextualizados a partir do Arquivo.pt.",
    emptyTitle: "Ainda não há notícias para mostrar",
    emptySummary: "Quando a fila de revisão tiver posts, esta área passa a mostrar a notícia principal.",
    docs: [
      {
        title: "Uma janela para o passado",
        body: "O Arquivo.pt é a fonte principal. O projeto encontra notícias antigas, organiza-as e volta a apresentá-las com o ano e a origem bem visíveis.",
        items: ["Cada história mantém a ligação à página preservada.", "O crédito ao Arquivo.pt acompanha todo o site."]
      },
      {
        title: "Escolha editorial",
        body: "As histórias são comparadas pela importância, interesse atual e diversidade de anos e fontes. Conteúdo repetido, promocional ou sem valor duradouro perde prioridade.",
        items: ["A seleção automática prepara as opções.", "A decisão de publicar passa por revisão humana."]
      },
      {
        title: "Explorar e confirmar",
        body: "O calendário reúne histórias do mesmo dia ao longo dos anos. A área de temas mostra como uma expressão aparece no tempo e permite filtrar por fonte.",
        items: ["As páginas individuais juntam contexto, imagem e fonte.", "Os posts publicados ficam ligados à respetiva história."]
      }
    ]
  },
  en: {
    navHome: "Home",
    navCalendar: "Calendar",
    navTopics: "Topics",
    navDocs: "Documentation",
    heroEyebrow: "Lead story",
    carouselEyebrow: "Editorial selection",
    carouselTitle: "Featured stories",
    latestEyebrow: "Social archive",
    latestTitle: "Latest published stories",
    latestPreviewNote: "No posts are marked as published yet; showing the prepared review queue.",
    latestPublishedNote: "Updates automatically when the publisher marks a post as published.",
    openInstagram: "View on Instagram",
    openArquivo: "Open on Arquivo.pt",
    unavailableInstagram: "Instagram link pending",
    unavailableSource: "Source pending",
    watermark: "Data collected via Arquivo.pt",
    originalYear: "Originally in",
    scheduledFor: "Prepared for",
    yearOnly: "in",
    calendarEyebrow: "Editorial calendar",
    calendarTitle: "Explore by date",
    calendarLead: "Pick a date and discover preserved stories for that day across the years.",
    calendarMonthLabel: "Month",
    calendarYearLabel: "Year",
    calendarDateLabel: "Choose date",
    calendarSourceLabel: "Recommendations from",
    calendarAllSources: "All newspapers",
    calendarPreviousDay: "Previous day",
    calendarNextDay: "Next day",
    calendarLoading: "Loading stories from this day...",
    calendarLoadError: "The recommendations for this day could not be loaded.",
    calendarNoResults: "No stories were found for this date and source.",
    dayRecommendationsTitle: "Important stories from this day:",
    openDay: "Open day",
    topicsEyebrow: "Historical search",
    topicsTitle: "How a topic evolved",
    topicsLead: "Compare a topic's presence in the preserved index over time and filter by source.",
    topicLabel: "Topic",
    topicSourceLabel: "Source",
    topicColorLabel: "Colour",
    topicShowValues: "Show values",
    topicAddAnalysis: "Add analysis",
    topicRemoveAnalysis: "Remove analysis",
    topicComparisonTitle: "Topic comparison",
    topicFromLabel: "From",
    topicToLabel: "To",
    topicSubmit: "Analyse",
    topicAllSources: "All sources",
    topicApiCredit: "Count verified against results indexed by Arquivo.pt.",
    topicLoadingNote: "This may take a while because of the large volume being analysed. For very broad searches, choose a source or shorten the range.",
    topicCoverageUneven: "Search coverage varies by year and source; zero means the index returned no results for that period.",
    topicLogScale: "Logarithmic scale used to keep years with fewer results visible.",
    topicCaptureNote: "Each value counts archived records matching the query. The same page may have been archived more than once.",
    topicMentions: "verified results",
    topicInstagramLegend: "Instagram post",
    topicDownload: "Download chart",
    topicDownloadFormat: "Download format",
    topicEmpty: "No results were found in this time range.",
    topicError: "The Arquivo.pt search could not be completed. Please try again shortly.",
    newsEyebrow: "Preserved story",
    newsOpenArquivo: "Open story on Arquivo.pt",
    newsOpenInstagram: "Open Instagram post",
    newsNotFound: "Story not found",
    newsNotFoundBody: "This address no longer matches an available story.",
    newsBack: "Back to the calendar",
    docsEyebrow: "Documentation",
    docsTitle: "How the project works",
    docsLead: "Notícias de Ontem brings preserved web stories back into view and lets people explore news memory by date and topic.",
    metricsEyebrow: "Project coverage",
    metricsTitle: "The project in numbers",
    metricNews: "Stories covered",
    metricNewsNote: "Stories found and organised by the project. The total grows as collection continues.",
    metricPublished: "Posts published",
    metricPublishedNote: "Posts already published by the project's accounts.",
    metricFollowers: "Followers",
    metricFollowersNote: "Combined followers across all of the project's social networks.",
    metricYears: "Years covered",
    metricSources: "Sources followed",
    docsGithubTitle: "Code and technical documentation",
    docsGithubBody: "Open GitHub for the full methodology, data notes and instructions for running the project.",
    footerCredit: "Data collected and contextualized from Arquivo.pt.",
    emptyTitle: "No stories to show yet",
    emptySummary: "When the review queue has posts, this area will show the lead story.",
    docs: [
      {
        title: "A window into the past",
        body: "Arquivo.pt is the primary source. The project finds older stories, organises them and presents them again with their year and origin clearly shown.",
        items: ["Every story keeps a link to the preserved page.", "Arquivo.pt is credited throughout the website."]
      },
      {
        title: "Editorial choice",
        body: "Stories are compared by importance, present-day interest and diversity of years and sources. Repetitive, promotional or short-lived material is given less weight.",
        items: ["Automated selection prepares the options.", "A human review decides what is published."]
      },
      {
        title: "Explore and verify",
        body: "The calendar brings together stories from the same day across different years. Topic search shows how a phrase appears over time and can be filtered by source.",
        items: ["Individual pages bring context, image and source together.", "Published posts link back to their story."]
      }
    ]
  },
};

function t(key) {
  return i18n[state.lang][key] || i18n.pt[key] || key;
}

function localized(item, field) {
  if (!item) return "";
  if (state.lang === "en" && item[`${field}_en`]) return item[`${field}_en`];
  return item[field] || "";
}

function decodedPathPart(value) {
  try {
    return decodeURIComponent(value).toLowerCase();
  } catch {
    return String(value || "").toLowerCase();
  }
}

function siteBasePath() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  const routeIndex = parts.findIndex((part) => ROUTE_SEGMENTS.has(decodedPathPart(part)));
  let baseParts = routeIndex >= 0 ? parts.slice(0, routeIndex) : [...parts];
  if (baseParts.length && /\.[a-z0-9]+$/i.test(baseParts[baseParts.length - 1])) {
    baseParts = baseParts.slice(0, -1);
  }
  return baseParts.length ? `/${baseParts.join("/")}/` : "/";
}

function assetPath(path) {
  if (!path || /^(https?:)?\/\//i.test(path) || /^(data|blob):/i.test(path)) return path || "";
  if (path.startsWith("/")) return path;
  const normalized = path.replace(/^(\.\.\/|\.\/)+/, "");
  return `${siteBasePath()}${normalized}`;
}

function routeUrl(routePath, params = {}) {
  const query = new URLSearchParams(params).toString();
  const normalizedRoute = String(routePath || "inicio").replace(/^\/+|\/+$/g, "");
  return `${siteBasePath()}${normalizedRoute}/${query ? `?${query}` : ""}`;
}

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = value || "";
}

function setLink(element, href, enabledLabel, disabledLabel) {
  if (!element) return;
  element.textContent = href ? enabledLabel : disabledLabel;
  if (href) {
    element.href = href;
    element.setAttribute("aria-disabled", "false");
  } else {
    element.removeAttribute("href");
    element.setAttribute("aria-disabled", "true");
  }
}

function formatDate(value) {
  if (!value) return "";
  const parts = String(value).split("-");
  if (parts.length < 3) return value;
  const date = new Date(`${parts[0]}-${parts[1]}-${parts[2]}T12:00:00`);
  return new Intl.DateTimeFormat(state.lang === "pt" ? "pt-PT" : "en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

function padNumber(value) {
  return String(value).padStart(2, "0");
}

function isoDate(year, month, day) {
  return `${year}-${padNumber(month)}-${padNumber(day)}`;
}

function todayIsoDate() {
  const now = new Date();
  return isoDate(now.getFullYear(), now.getMonth() + 1, now.getDate());
}

function monthDay(value) {
  return String(value || "").slice(5, 10);
}

function titleKey(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s]/g, "")
    .split(/\s+/)
    .filter((word) => word.length > 2)
    .slice(0, 12)
    .join(" ");
}

function dateYear(value) {
  const year = Number(String(value || "").slice(0, 4));
  return Number.isFinite(year) ? year : new Date().getFullYear();
}

function isValidIsoDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))) return false;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day;
}

function selectedDateFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const queryDate = params.get("data");
  if (isValidIsoDate(queryDate)) return queryDate;
  const pathDate = decodeURIComponent(window.location.pathname).match(/\/(\d{4}-\d{2}-\d{2})\/?$/);
  if (pathDate && isValidIsoDate(pathDate[1])) return pathDate[1];
  return "";
}

function ensureCalendarDate() {
  const fromUrl = selectedDateFromLocation();
  state.selectedDate = fromUrl || todayIsoDate();
  state.calendarYear = dateYear(state.selectedDate);
  state.calendarMonth = Number(state.selectedDate.slice(5, 7));
  if (state.calendarPickerVisible === null) state.calendarPickerVisible = !fromUrl;
}

function monthName(monthIndex) {
  const date = new Date(2026, monthIndex, 1);
  return new Intl.DateTimeFormat(state.lang === "pt" ? "pt-PT" : "en-GB", { month: "long" }).format(date);
}

function itemMeta(item) {
  return item.category ? [item.category] : [];
}

function titleWithYear(item) {
  const title = localized(item, "title");
  const year = String(item?.original_year || "").trim();
  if (!title || !year || new RegExp(`\\b${year}\\b`).test(title)) return title;
  return `${title} ${t("yearOnly")} ${year}`;
}

function newsPageUrl(item) {
  return item?.page_id
    ? `${siteBasePath()}noticia/${encodeURIComponent(item.page_id)}/`
    : "";
}

function setMetaContent(selector, value) {
  const element = document.head.querySelector(selector);
  if (element && value) element.setAttribute("content", value);
}

function absolutePageUrl(path) {
  return new URL(path, window.location.origin).href;
}

function updateDocumentMetadata() {
  const route = state.route || routeFromLocation();
  const routeSeo = {
    home: {
      title: "Notícias de Ontem | Memória da imprensa portuguesa",
      description: "Explore notícias preservadas pelo Arquivo.pt, compare diferentes anos e descubra a memória da imprensa portuguesa em cada dia.",
      path: routeUrl("inicio"),
      type: "website",
    },
    calendar: {
      title: "Calendário de notícias históricas | Notícias de Ontem",
      description: "Escolha uma data e descubra notícias de diferentes anos preservadas pelo Arquivo.pt.",
      path: routeUrl("calendario"),
      type: "website",
    },
    topics: {
      title: "Evolução de temas na imprensa portuguesa | Notícias de Ontem",
      description: "Analise a evolução de temas na imprensa portuguesa preservada e filtre os resultados por jornal e período.",
      path: routeUrl("temas"),
      type: "website",
    },
    docs: {
      title: "Como funciona o projeto | Notícias de Ontem",
      description: "Conheça as fontes, a cobertura e o método usado para selecionar conteúdos preservados pelo Arquivo.pt.",
      path: routeUrl("documentacao"),
      type: "website",
    },
  };
  let seo = routeSeo[route] || routeSeo.home;
  let robots = "index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1";
  let image = absolutePageUrl(`${siteBasePath()}assets/icon.png`);
  let structured = {
    "@context": "https://schema.org",
    "@type": route === "calendar" ? "CollectionPage" : route === "topics" ? "SearchResultsPage" : "WebPage",
    name: seo.title,
    description: seo.description,
    url: absolutePageUrl(seo.path),
    inLanguage: "pt-PT",
    isBasedOn: "https://arquivo.pt/",
  };

  if (route === "news") {
    const item = findNewsItem(selectedNewsIdFromLocation());
    if (item) {
      const title = titleWithYear(item);
      seo = {
        title: `${title} | Notícias de Ontem`,
        description: localized(item, "summary") || `Consulte ${title} e a fonte preservada no Arquivo.pt.`,
        path: newsPageUrl(item),
        type: "article",
      };
      image = absolutePageUrl(assetPath(item.detail_image || item.image || item.banner_image || "assets/icon.png"));
      if (String(item.status || "").toLowerCase() === "pending") robots = "noindex,follow";
      structured = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        headline: title,
        description: seo.description,
        url: absolutePageUrl(seo.path),
        mainEntityOfPage: absolutePageUrl(seo.path),
        image: [image],
        datePublished: item.date || undefined,
        articleSection: item.category || undefined,
        inLanguage: "pt-PT",
        isBasedOn: item.source_url || "https://arquivo.pt/",
        publisher: {
          "@type": "Organization",
          name: "Notícias de Ontem",
          url: absolutePageUrl(siteBasePath()),
        },
      };
    } else {
      seo = {
        title: "Notícia não encontrada | Notícias de Ontem",
        description: "A notícia pedida não está disponível.",
        path: window.location.pathname,
        type: "website",
      };
      robots = "noindex,follow";
    }
  }

  const canonical = absolutePageUrl(seo.path);
  document.title = seo.title;
  setMetaContent('meta[name="description"]', seo.description);
  setMetaContent('meta[name="robots"]', robots);
  setMetaContent('meta[property="og:type"]', seo.type);
  setMetaContent('meta[property="og:title"]', seo.title);
  setMetaContent('meta[property="og:description"]', seo.description);
  setMetaContent('meta[property="og:url"]', canonical);
  setMetaContent('meta[property="og:image"]', image);
  setMetaContent('meta[property="og:image:alt"]', seo.title);
  setMetaContent('meta[name="twitter:title"]', seo.title);
  setMetaContent('meta[name="twitter:description"]', seo.description);
  setMetaContent('meta[name="twitter:image"]', image);
  const canonicalLink = document.head.querySelector('link[rel="canonical"]');
  if (canonicalLink) canonicalLink.href = canonical;
  const structuredData = document.getElementById("structured-data");
  if (structuredData) structuredData.textContent = JSON.stringify(structured);
}

function renderHero() {
  const heroItems = state.data?.carousel?.length ? state.data.carousel : [state.data?.featured].filter(Boolean);
  const item = heroItems.length ? heroItems[state.slide % heroItems.length] : null;
  const hero = document.getElementById("hero");
  const instagram = document.getElementById("hero-instagram");
  const source = document.getElementById("hero-source");
  const detail = document.getElementById("hero-detail");
  if (!item) {
    hero.style.backgroundImage = `url('${assetPath("assets/icon.png")}')`;
    setText("#hero-detail", t("emptyTitle"));
    detail?.removeAttribute("href");
    setText("#hero-year", "");
    setText("#hero-summary", t("emptySummary"));
    setLink(instagram, "", t("openInstagram"), t("unavailableInstagram"));
    setLink(source, "", t("openArquivo"), t("unavailableSource"));
    if (instagram) instagram.hidden = true;
    if (source) source.hidden = true;
    return;
  }

  hero.style.backgroundImage = `url('${assetPath(item.banner_image || item.image || "assets/icon.png")}')`;
  setText("#hero-detail", localized(item, "title"));
  if (detail && item.page_id) {
    detail.href = newsPageUrl(item);
    detail.dataset.newsId = item.page_id;
  }
  const year = item.original_year ? `${t("yearOnly")} ${item.original_year}` : "";
  setText("#hero-year", year);
  setText("#hero-summary", localized(item, "summary"));
  setLink(instagram, item.instagram_url, t("openInstagram"), t("unavailableInstagram"));
  setLink(source, item.source_url, t("openArquivo"), t("unavailableSource"));
  // Um botão sem destino sai do hero em vez de aparecer desativado.
  if (instagram) instagram.hidden = !item.instagram_url;
  if (source) source.hidden = !item.source_url;
}

function cardImage(item, linked = false) {
  const src = assetPath(item.image || "assets/icon.png");
  const image = `<img src="${escapeHtml(src)}" alt="">`;
  if (!linked || !item.page_id) return image;
  return `<a class="card-image-link" href="${escapeHtml(newsPageUrl(item))}" data-news-id="${escapeHtml(item.page_id)}" aria-label="${escapeHtml(titleWithYear(item))}">${image}</a>`;
}

function renderCarousel() {
  const carousel = document.getElementById("carousel");
  if (!carousel) return;
  const items = state.data?.carousel || [];
  carousel.innerHTML = `<div class="carousel-track">${items.map((item) => {
    const meta = itemMeta(item).map(escapeHtml).join(" · ");
    return `
      <article class="story-card" style="background-image: url('${escapeHtml(assetPath(item.banner_image || item.image || "assets/icon.png"))}')">
        <div class="story-shade"></div>
        <div class="content">
          <div class="meta">${meta}</div>
          <h3><a href="${escapeHtml(newsPageUrl(item))}" data-news-id="${escapeHtml(item.page_id)}">${escapeHtml(titleWithYear(item))}</a></h3>
          <p>${escapeHtml(localized(item, "summary"))}</p>
          <div class="card-actions">
            ${item.instagram_url ? `<a class="text-link" href="${escapeHtml(item.instagram_url)}" target="_blank" rel="noreferrer">${escapeHtml(t("openInstagram"))}</a>` : ""}
            ${item.source_url ? `<a class="text-link" href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(t("openArquivo"))}</a>` : ""}
          </div>
        </div>
      </article>
    `;
  }).join("")}</div>`;
}

function renderLatest() {
  const items = state.data?.latest || [];
  const grid = document.getElementById("latest-grid");
  const note = state.data?.has_published_posts ? t("latestPublishedNote") : t("latestPreviewNote");
  setText("#latest-note", note);
  grid.innerHTML = items.map((item) => {
    const meta = itemMeta(item).map(escapeHtml).join(" · ");
    return `
      <article class="latest-card">
        ${cardImage(item, true)}
        <div class="content">
          <div class="meta">${meta}</div>
          <h3><a href="${escapeHtml(newsPageUrl(item))}" data-news-id="${escapeHtml(item.page_id)}">${escapeHtml(titleWithYear(item))}</a></h3>
          <p>${escapeHtml(formatDate(item.date))}</p>
          <div class="card-actions">
            ${item.instagram_url ? `<a class="text-link" href="${escapeHtml(item.instagram_url)}" target="_blank" rel="noreferrer">${escapeHtml(t("openInstagram"))}</a>` : ""}
            ${item.source_url ? `<a class="text-link" href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(t("openArquivo"))}</a>` : ""}
          </div>
        </div>
      </article>
    `;
  }).join("");
}

function calendarPostsForDate(dateValue) {
  const selectedYear = dateYear(dateValue);
  const targetYears = new Set([selectedYear, selectedYear - 1]);
  const targetMonthDay = monthDay(dateValue);
  return (state.data?.all || [])
    .filter((item) => monthDay(item.date) === targetMonthDay && targetYears.has(dateYear(item.date)))
    .sort((a, b) => `${b.date}-${b.slot || 0}`.localeCompare(`${a.date}-${a.slot || 0}`))
    .slice(0, state.data?.calendar?.top_instagram_posts || 4);
}

function calendarRecommendationsForDate(dateValue, usedItems) {
  const targetMonthDay = monthDay(dateValue);
  const selectedYear = dateYear(dateValue);
  const usedKeys = new Set((usedItems || []).map((item) => titleKey(localized(item, "title")) || item.source_url || item.id));
  const candidates = state.apiBaseUrl
    ? state.calendarRecommendations
    : (state.data?.calendar?.recommendations_by_day?.[targetMonthDay] || []);
  const beforeOrSameYear = [];
  const afterYear = [];
  candidates.forEach((item) => {
    if (state.calendarSource && item.domain !== state.calendarSource) return;
    const key = titleKey(localized(item, "title")) || item.source_url || item.id;
    if (usedKeys.has(key)) return;
    if (dateYear(item.date) <= selectedYear) beforeOrSameYear.push(item);
    else afterYear.push(item);
  });
  const ordered = [...beforeOrSameYear, ...afterYear];
  if (state.calendarSource) return ordered;
  const bySource = new Map();
  ordered.forEach((item) => {
    const source = item.domain || item.source_profile || "arquivo.pt";
    if (!bySource.has(source)) bySource.set(source, []);
    bySource.get(source).push(item);
  });
  const balanced = [];
  while ([...bySource.values()].some((items) => items.length)) {
    bySource.forEach((items) => {
      if (items.length) balanced.push(items.shift());
    });
  }
  return balanced;
}

function calendarSourcesForDate(dateValue) {
  const configured = state.data?.topic_search?.sources || [];
  const candidates = state.data?.calendar?.recommendations_by_day?.[monthDay(dateValue)] || [];
  return [...new Set([...configured, ...candidates.map((item) => item.domain)].filter(Boolean))]
    .sort((left, right) => topicSourceLabel(left).localeCompare(topicSourceLabel(right), state.lang));
}

function renderCalendarNavigation() {
  const picker = document.getElementById("calendar-date-picker");
  const source = document.getElementById("calendar-source");
  const largePicker = document.getElementById("calendar-picker-panel");
  if (picker) picker.value = state.selectedDate;
  if (largePicker) largePicker.hidden = !state.calendarPickerVisible;
  if (!source) return;
  const sources = calendarSourcesForDate(state.selectedDate);
  if (state.calendarSource && !sources.includes(state.calendarSource)) state.calendarSource = "";
  source.innerHTML = [
    `<option value="">${escapeHtml(t("calendarAllSources"))}</option>`,
    ...sources.map((domain) => `<option value="${escapeHtml(domain)}"${domain === state.calendarSource ? " selected" : ""}>${escapeHtml(topicSourceLabel(domain))}</option>`),
  ].join("");
}

function storyCard(item, options = {}) {
  const meta = itemMeta(item).map(escapeHtml).join(" · ");
  const imageHtml = options.compactImage ? cardImage(item, true) : "";
  return `
    <article class="${options.className || "latest-card"}">
      ${imageHtml}
      <div class="content">
        <div class="meta">${meta}</div>
        <h3><a href="${escapeHtml(newsPageUrl(item))}" data-news-id="${escapeHtml(item.page_id)}">${escapeHtml(titleWithYear(item))}</a></h3>
        ${options.showDate ? `<p>${escapeHtml(formatDate(item.date))}</p>` : ""}
        ${localized(item, "summary") ? `<p>${escapeHtml(localized(item, "summary"))}</p>` : ""}
        <div class="card-actions">
          ${item.instagram_url ? `<a class="text-link" href="${escapeHtml(item.instagram_url)}" target="_blank" rel="noreferrer">${escapeHtml(t("openInstagram"))}</a>` : ""}
          ${item.source_url ? `<a class="text-link" href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(t("openArquivo"))}</a>` : ""}
        </div>
      </div>
    </article>
  `;
}

function renderCalendarMonthOptions() {
  const select = document.getElementById("calendar-month");
  if (!select) return;
  select.innerHTML = Array.from({ length: 12 }, (_, index) => {
    const value = index + 1;
    return `<option value="${value}" ${value === state.calendarMonth ? "selected" : ""}>${escapeHtml(monthName(index))}</option>`;
  }).join("");
}

function renderCalendarGrid() {
  const grid = document.getElementById("calendar-grid");
  const yearInput = document.getElementById("calendar-year");
  if (!grid || !yearInput) return;

  renderCalendarMonthOptions();
  yearInput.value = state.calendarYear;

  const firstDay = new Date(state.calendarYear, state.calendarMonth - 1, 1);
  const daysInMonth = new Date(state.calendarYear, state.calendarMonth, 0).getDate();
  const offset = (firstDay.getDay() + 6) % 7;
  const postDates = new Set(state.data?.calendar?.post_dates || []);
  const recommendationDays = state.data?.calendar?.recommendations_by_day || {};
  const weekdayLabels = state.lang === "pt"
    ? ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  const cells = weekdayLabels.map((label) => `<div class="calendar-weekday">${escapeHtml(label)}</div>`);
  for (let i = 0; i < offset; i += 1) {
    cells.push('<div class="calendar-empty"></div>');
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    const dateValue = isoDate(state.calendarYear, state.calendarMonth, day);
    const hasPosts = postDates.has(dateValue) || postDates.has(isoDate(state.calendarYear - 1, state.calendarMonth, day));
    const hasRecommendations = Boolean(recommendationDays[monthDay(dateValue)]?.length);
    const active = dateValue === state.selectedDate;
    cells.push(`
      <button type="button" class="calendar-day ${active ? "active" : ""}" data-date="${dateValue}">
        <span>${day}</span>
        <small>${hasPosts || hasRecommendations ? "•" : ""}</small>
      </button>
    `);
  }
  grid.innerHTML = cells.join("");
}

function renderDayPanel() {
  const panel = document.getElementById("day-panel");
  if (!panel) return;
  const posts = state.calendarSource ? [] : calendarPostsForDate(state.selectedDate);
  const targetTotal = state.data?.calendar?.target_total_per_day || 25;
  const recommendationLimit = Math.max(targetTotal - posts.length, 0);
  const recommendations = calendarRecommendationsForDate(state.selectedDate, posts).slice(0, recommendationLimit);
  const stateMessage = state.calendarLoading
    ? `<p class="calendar-status">${escapeHtml(t("calendarLoading"))}</p>`
    : state.calendarError
      ? `<p class="calendar-status error">${escapeHtml(t("calendarLoadError"))}</p>`
      : (!posts.length && !recommendations.length)
        ? `<p class="calendar-status">${escapeHtml(t("calendarNoResults"))}</p>`
        : "";

  panel.innerHTML = `
    <div class="day-panel-heading">
      <div>
        <p class="eyebrow">${escapeHtml(formatDate(state.selectedDate))}</p>
        <h2>${escapeHtml(t("dayRecommendationsTitle"))}</h2>
      </div>
    </div>
    ${stateMessage}
    ${posts.length ? `<div class="day-post-grid">${posts.map((item) => storyCard(item, { compactImage: true, showDate: true })).join("")}</div>` : ""}
    ${recommendations.length ? `<ol class="recommendation-list">${recommendations.map((item) => `
      <li>
        <a href="${escapeHtml(newsPageUrl(item))}" data-news-id="${escapeHtml(item.page_id)}">
          <span>${escapeHtml(item.original_year || dateYear(item.date))}</span>
          <strong>${escapeHtml(localized(item, "title"))}</strong>
          <em>${escapeHtml([topicSourceLabel(item.domain || item.source_profile), "Arquivo.pt"].filter(Boolean).join(" · "))}</em>
        </a>
      </li>
    `).join("")}</ol>` : ""}
  `;
}

async function loadCalendarRecommendations() {
  if (!state.apiBaseUrl || !state.selectedDate) return;
  state.calendarRequest?.abort();
  const controller = new AbortController();
  state.calendarRequest = controller;
  state.calendarLoading = true;
  state.calendarError = "";
  state.calendarRecommendations = [];
  renderDayPanel();
  const params = new URLSearchParams({ selected_date: state.selectedDate, limit: "25" });
  if (state.calendarSource) params.set("source", state.calendarSource);
  try {
    const response = await fetch(`${state.apiBaseUrl}/calendar-recommendations?${params}`, {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Calendar API ${response.status}`);
    const payload = await response.json();
    state.calendarRecommendations = Array.isArray(payload.items) ? payload.items : [];
  } catch (error) {
    if (error.name === "AbortError") return;
    state.calendarError = error.message || "calendar_error";
  } finally {
    if (state.calendarRequest === controller) {
      state.calendarLoading = false;
      state.calendarRequest = null;
      renderDayPanel();
    }
  }
}

function renderCalendar() {
  if (!state.data) return;
  ensureCalendarDate();
  renderCalendarNavigation();
  renderCalendarGrid();
  renderDayPanel();
  loadCalendarRecommendations();
}

function selectedNewsIdFromLocation() {
  const pathMatch = decodeURIComponent(window.location.pathname).match(/\/noticia\/([^/]+)\/?$/i);
  if (pathMatch) return pathMatch[1];
  return new URLSearchParams(window.location.search).get("id") || "";
}

function findNewsItem(pageId) {
  if (!pageId) return null;
  const post = (state.data?.all || []).find((item) => item.page_id === pageId);
  if (post) return post;
  if (state.dynamicNews[pageId]) return state.dynamicNews[pageId];
  const dynamicRecommendation = state.calendarRecommendations.find((item) => item.page_id === pageId);
  if (dynamicRecommendation) return dynamicRecommendation;
  const recommendationDays = state.data?.calendar?.recommendations_by_day || {};
  for (const items of Object.values(recommendationDays)) {
    const match = (items || []).find((item) => item.page_id === pageId);
    if (match) return match;
  }
  return null;
}

async function loadDynamicNewsItem(pageId) {
  if (!state.apiBaseUrl || !pageId || state.newsRequestId === pageId || state.dynamicNews[pageId]) return;
  state.newsRequestId = pageId;
  try {
    const response = await fetch(`${state.apiBaseUrl}/news/${encodeURIComponent(pageId)}`, { cache: "no-store" });
    if (!response.ok) return;
    state.dynamicNews[pageId] = await response.json();
    if (selectedNewsIdFromLocation() === pageId) renderNewsDetail();
  } finally {
    if (state.newsRequestId === pageId) state.newsRequestId = "";
  }
}

function renderNewsDetail() {
  const container = document.getElementById("news-detail");
  if (!container) return;
  const item = findNewsItem(selectedNewsIdFromLocation());
  if (!item) {
    loadDynamicNewsItem(selectedNewsIdFromLocation());
    container.innerHTML = `
      <div class="news-not-found">
        <p class="eyebrow">${escapeHtml(t("newsEyebrow"))}</p>
        <h1 id="news-detail-title">${escapeHtml(t("newsNotFound"))}</h1>
        <p>${escapeHtml(t("newsNotFoundBody"))}</p>
        <a class="button primary" href="${escapeHtml(routeUrl("calendário"))}" data-route-link="calendar">${escapeHtml(t("newsBack"))}</a>
      </div>
    `;
    updateDocumentMetadata();
    return;
  }

  const title = titleWithYear(item);
  const sourceName = item.domain || item.source_profile || "Arquivo.pt";
  const image = assetPath(item.detail_image || item.image || item.banner_image || "assets/icon.png");
  const meta = [item.category, sourceName].filter(Boolean).join(" · ");
  container.innerHTML = `
    <div class="news-detail-copy">
      <p class="eyebrow">${escapeHtml(t("newsEyebrow"))}</p>
      <p class="news-detail-meta">${escapeHtml(meta)}</p>
      <h1 id="news-detail-title">${escapeHtml(title)}</h1>
      <p class="news-detail-summary">${escapeHtml(localized(item, "summary"))}</p>
      <div class="news-detail-actions">
        ${item.instagram_url ? `<a class="button primary" href="${escapeHtml(item.instagram_url)}" target="_blank" rel="noreferrer">${escapeHtml(t("newsOpenInstagram"))}</a>` : ""}
        ${item.source_url ? `<a class="button secondary" href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(t("newsOpenArquivo"))}</a>` : ""}
      </div>
    </div>
    <figure class="news-detail-figure">
      <img id="news-detail-image" src="${escapeHtml(image)}" alt="${escapeHtml(title)}">
    </figure>
  `;
  const detailImage = document.getElementById("news-detail-image");
  detailImage?.addEventListener("error", () => {
    const fallback = assetPath("assets/icon.png");
    if (detailImage.src !== fallback) detailImage.src = fallback;
  }, { once: true });
  updateDocumentMetadata();
}

function normalizedTopicText(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const TOPIC_DEFAULT_COLORS = ["#0d9ba8", "#33526b", "#c85d4b", "#9b6b2f"];
const TOPIC_MAX_ANALYSES = 4;

function validTopicColor(value, fallback = TOPIC_DEFAULT_COLORS[0]) {
  return /^#[0-9a-f]{6}$/i.test(String(value || "")) ? value.toLowerCase() : fallback;
}

function normalizedTopicAnalysis(analysis = {}, index = 0) {
  return {
    query: String(analysis.query || "").trim(),
    source: String(analysis.source || "").trim(),
    color: validTopicColor(analysis.color, TOPIC_DEFAULT_COLORS[index % TOPIC_DEFAULT_COLORS.length]),
  };
}

function collectTopicAnalysesFromForm() {
  const rows = Array.from(document.querySelectorAll("[data-topic-analysis]"));
  if (!rows.length) return state.topicAnalyses.length ? state.topicAnalyses : [normalizedTopicAnalysis({}, 0)];
  return rows.slice(0, TOPIC_MAX_ANALYSES).map((row, index) => normalizedTopicAnalysis({
    query: row.querySelector("[data-topic-query]")?.value || "",
    source: row.querySelector("[data-topic-source]")?.value || "",
    color: row.querySelector("[data-topic-color]")?.value || TOPIC_DEFAULT_COLORS[index],
  }, index));
}

function topicAnalysisLocationParams(analyses) {
  const params = {};
  analyses.forEach((analysis, index) => {
    const suffix = index ? String(index + 1) : "";
    params[`tema${suffix}`] = analysis.query;
    if (analysis.source) params[`fonte${suffix}`] = analysis.source;
    params[`cor${suffix}`] = analysis.color;
  });
  return params;
}

function matchingInstagramPosts(query, source, fromDate, toDate) {
  const terms = normalizedTopicText(query).split(" ").filter(Boolean);
  if (!terms.length) return [];
  const fromYear = Number(String(fromDate || "").slice(0, 4));
  const toYear = Number(String(toDate || "").slice(0, 4));
  return (state.data?.all || []).filter((item) => {
    if (!item.instagram_url) return false;
    const year = Number(item.original_year);
    if (!Number.isFinite(year) || year < fromYear || year > toYear) return false;
    const itemSource = `${item.domain || ""} ${item.source_profile || ""} ${item.source_url || ""}`.toLowerCase();
    if (source && !itemSource.includes(source)) return false;
    const text = normalizedTopicText(`${localized(item, "title")} ${localized(item, "summary")}`);
    return terms.every((term) => text.includes(term));
  });
}

function topicCacheKey(query, source, fromDate, toDate) {
  return `ndo-topic-v3-verified:${normalizedTopicText(query)}:${source}:${fromDate}:${toDate}`;
}

function readTopicCache(key) {
  try {
    const cached = JSON.parse(localStorage.getItem(key) || "null");
    if (!cached || cached.verified !== true || !Array.isArray(cached.series)) return null;
    if (Date.now() - Number(cached.savedAt || 0) > 24 * 60 * 60 * 1000) return null;
    return cached;
  } catch {
    return null;
  }
}

function writeTopicCache(key, result) {
  try {
    localStorage.setItem(key, JSON.stringify({
      savedAt: Date.now(),
      verified: true,
      series: result.series,
      total: result.total,
    }));
  } catch {
    // The graph still works when private browsing disables local storage.
  }
}

function topicSearchHosts(source) {
  if (!source) return [];
  const configured = state.data?.topic_search?.source_metadata?.[source]?.search_hosts;
  const hosts = Array.isArray(configured) && configured.length ? configured : [`www.${source}`, source];
  return [...new Set(hosts.map((host) => String(host || "").trim()).filter(Boolean))];
}

function topicApiBoundary(value, endOfDay = false) {
  const text = String(value || "");
  if (/^\d{14}$/.test(text)) return text;
  return `${text.replaceAll("-", "")}${endOfDay ? "235959" : "000000"}`;
}

function topicSearchUrl(query, source, fromValue, toValue, options = {}) {
  const params = new URLSearchParams({
    q: query,
    from: topicApiBoundary(fromValue, false),
    to: topicApiBoundary(toValue, true),
    maxItems: String(options.maxItems ?? 1),
    offset: String(options.offset ?? 0),
    dedupValue: "0",
  });
  topicSearchHosts(source).forEach((host) => params.append("siteSearch", host));
  return `https://arquivo.pt/textsearch?${params.toString()}`;
}

async function fetchTopicProbe(query, source, fromTimestamp, toTimestamp, offset, parentSignal) {
  let lastError = null;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if (parentSignal?.aborted) throw new DOMException("Aborted", "AbortError");
    const budget = topicProbeBudgets.get(parentSignal);
    if (budget && budget.used >= budget.maximum) {
      const error = new Error("Topic verification limit reached");
      error.code = "verification_limit";
      throw error;
    }
    if (budget) budget.used += 1;
    const controller = new AbortController();
    const abortRequest = () => controller.abort();
    parentSignal?.addEventListener("abort", abortRequest, { once: true });
    const timeout = window.setTimeout(() => controller.abort(), 45000);
    try {
      await waitForTopicRequestSlot(parentSignal);
      const response = await fetch(topicSearchUrl(query, source, fromTimestamp, toTimestamp, { offset }), {
        signal: controller.signal,
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`Arquivo.pt ${response.status}`);
      const payload = await response.json();
      const rawEstimate = String(payload.estimated_nr_results ?? payload.estimatedNrResults ?? "0");
      const estimate = Number(rawEstimate.replace(/[^0-9]/g, "")) || 0;
      const items = payload.response_items || payload.responseItems || [];
      return { hasResult: Array.isArray(items) && items.length > 0, estimate };
    } catch (error) {
      if (parentSignal?.aborted) throw error;
      lastError = error;
      if (attempt < 2) await new Promise((resolve) => window.setTimeout(resolve, 450 * (attempt + 1)));
    } finally {
      window.clearTimeout(timeout);
      parentSignal?.removeEventListener("abort", abortRequest);
    }
  }
  throw lastError || new Error("Arquivo.pt unavailable");
}

function updateTopicProgress(done, total) {
  const progress = document.getElementById("topic-progress");
  const bar = document.getElementById("topic-progress-bar");
  const text = document.getElementById("topic-progress-text");
  if (!progress || !bar || !text) return;
  const percent = total ? Math.round((done / total) * 100) : 100;
  progress.hidden = false;
  bar.max = 100;
  bar.value = percent;
  text.textContent = state.lang === "pt" ? `A carregar ${percent}%` : `Loading ${percent}%`;
}

function normalizedApiBaseUrl(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  return raw.replace(/\/+$/, "");
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 3000) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const parentSignal = options.signal;
  const abortRequest = () => controller.abort();
  parentSignal?.addEventListener("abort", abortRequest, { once: true });
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    window.clearTimeout(timeout);
    parentSignal?.removeEventListener("abort", abortRequest);
  }
}

async function loadDynamicRuntimeData() {
  if (state.data?.runtime_mode === "static") return;
  const configured = normalizedApiBaseUrl(state.data?.api_base_url);
  const sameOriginCandidate = window.location.protocol.startsWith("http") ? "/api" : "";
  const candidate = configured || sameOriginCandidate;
  if (!candidate) return;
  try {
    const health = await fetchWithTimeout(`${candidate}/health`, { cache: "no-store" }, 2200);
    if (!health.ok) return;
    const [siteDataResponse, coverageResponse, metricsResponse, searchStatusResponse] = await Promise.all([
      fetchWithTimeout(`${candidate}/site-data`, { cache: "no-store" }, 6000),
      fetchWithTimeout(`${candidate}/coverage`, { cache: "no-store" }, 4000),
      fetchWithTimeout(`${candidate}/metrics`, { cache: "no-store" }, 4000),
      fetchWithTimeout(`${candidate}/search-status`, { cache: "no-store" }, 4000),
    ]);
    state.apiBaseUrl = candidate;
    if (siteDataResponse.ok) {
      const dynamicData = await siteDataResponse.json();
      if (dynamicData && typeof dynamicData === "object") state.data = dynamicData;
    }
    if (coverageResponse.ok) {
      const coverage = await coverageResponse.json();
      state.data.topic_search = {
        ...(state.data.topic_search || {}),
        ...coverage,
        source_metadata: {
          ...(state.data.topic_search?.source_metadata || {}),
          ...(coverage.source_metadata || {}),
        },
      };
    }
    if (metricsResponse.ok) {
      state.data.metrics = {
        ...(state.data.metrics || {}),
        ...(await metricsResponse.json()),
      };
    }
    if (searchStatusResponse.ok) {
      state.data.topic_search = state.data.topic_search || {};
      state.data.topic_search.search_status = await searchStatusResponse.json();
    }
  } catch {
    state.apiBaseUrl = "";
  }
}

function waitForTopicPoll(milliseconds, signal) {
  return abortableTopicDelay(milliseconds, signal);
}

async function fetchTopicSeriesFromBackend(analyses, fromDate, toDate, showValues, signal) {
  const createResponse = await fetch(`${state.apiBaseUrl}/topic-analyses`, {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      analyses,
      from_date: fromDate,
      to_date: toDate,
      show_values: showValues,
    }),
  });
  if (!createResponse.ok) {
    const payload = await createResponse.json().catch(() => ({}));
    const error = new Error(payload?.detail?.message || payload?.detail || `API ${createResponse.status}`);
    error.code = createResponse.status === 422 ? "invalid_coverage" : "request_failed";
    throw error;
  }
  const created = await createResponse.json();
  while (!signal.aborted) {
    const response = await fetch(`${state.apiBaseUrl}/topic-analyses/${encodeURIComponent(created.id)}`, {
      signal,
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`API ${response.status}`);
    const job = await response.json();
    updateTopicProgress(Number(job.progress) || 0, 100);
    if (job.status === "completed" && job.result) return job.result;
    if (job.status === "failed") throw new Error(job.error || "Analysis failed");
    await waitForTopicPoll(900, signal);
  }
  throw new DOMException("Aborted", "AbortError");
}

const TOPIC_EXACT_SLICE_LIMIT = 1800;
const TOPIC_MAX_PROBES_PER_SEARCH = 360;
const TOPIC_MIN_REQUEST_INTERVAL_MS = 310;
const topicProbeBudgets = new WeakMap();
let nextTopicRequestAt = 0;
let topicRequestQueue = Promise.resolve();

function abortableTopicDelay(milliseconds, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const abortRequest = () => {
      window.clearTimeout(timeout);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timeout = window.setTimeout(() => {
      signal?.removeEventListener("abort", abortRequest);
      resolve();
    }, Math.max(0, milliseconds));
    signal?.addEventListener("abort", abortRequest, { once: true });
  });
}

function waitForTopicRequestSlot(signal) {
  const requestSlot = topicRequestQueue.then(async () => {
    const delay = Math.max(0, nextTopicRequestAt - Date.now());
    if (delay) await abortableTopicDelay(delay, signal);
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    nextTopicRequestAt = Date.now() + TOPIC_MIN_REQUEST_INTERVAL_MS;
  });
  topicRequestQueue = requestSlot.catch(() => {});
  return requestSlot;
}

async function firstEmptyTopicOffset(query, source, fromTimestamp, toTimestamp, lowPresent, highEmpty, signal) {
  let low = lowPresent;
  let high = highEmpty;
  while (high - low > 1) {
    const middle = Math.floor((low + high) / 2);
    const probe = await fetchTopicProbe(query, source, fromTimestamp, toTimestamp, middle, signal);
    if (probe.hasResult) low = middle;
    else high = middle;
  }
  return high;
}

async function verifiedTopicIntervalCount(query, source, fromTimestamp, toTimestamp, signal) {
  const first = await fetchTopicProbe(query, source, fromTimestamp, toTimestamp, 0, signal);
  if (!first.hasResult) return 0;

  const hint = Math.max(0, Number(first.estimate) || 0);
  if (hint > 0 && hint <= TOPIC_EXACT_SLICE_LIMIT) {
    const beforePromise = hint === 1
      ? Promise.resolve(first)
      : fetchTopicProbe(query, source, fromTimestamp, toTimestamp, hint - 1, signal);
    const afterPromise = fetchTopicProbe(query, source, fromTimestamp, toTimestamp, hint, signal);
    const [before, after] = await Promise.all([beforePromise, afterPromise]);
    if (before.hasResult && !after.hasResult) return hint;
    if (!before.hasResult) {
      return firstEmptyTopicOffset(query, source, fromTimestamp, toTimestamp, 0, hint - 1, signal);
    }
    const limit = hint === TOPIC_EXACT_SLICE_LIMIT
      ? after
      : await fetchTopicProbe(query, source, fromTimestamp, toTimestamp, TOPIC_EXACT_SLICE_LIMIT, signal);
    if (limit.hasResult) return null;
    return firstEmptyTopicOffset(query, source, fromTimestamp, toTimestamp, hint, TOPIC_EXACT_SLICE_LIMIT, signal);
  }

  const limit = await fetchTopicProbe(
    query,
    source,
    fromTimestamp,
    toTimestamp,
    TOPIC_EXACT_SLICE_LIMIT,
    signal,
  );
  if (limit.hasResult) return null;
  return firstEmptyTopicOffset(query, source, fromTimestamp, toTimestamp, 0, TOPIC_EXACT_SLICE_LIMIT, signal);
}

function topicTimestampToSeconds(value) {
  const text = String(value || "");
  return Math.floor(Date.UTC(
    Number(text.slice(0, 4)),
    Number(text.slice(4, 6)) - 1,
    Number(text.slice(6, 8)),
    Number(text.slice(8, 10)),
    Number(text.slice(10, 12)),
    Number(text.slice(12, 14)),
  ) / 1000);
}

function topicSecondsToTimestamp(seconds) {
  const date = new Date(seconds * 1000);
  const part = (value) => String(value).padStart(2, "0");
  return `${date.getUTCFullYear()}${part(date.getUTCMonth() + 1)}${part(date.getUTCDate())}${part(date.getUTCHours())}${part(date.getUTCMinutes())}${part(date.getUTCSeconds())}`;
}

async function countTopicIntervalExactly(query, source, fromTimestamp, toTimestamp, signal) {
  const directCount = await verifiedTopicIntervalCount(query, source, fromTimestamp, toTimestamp, signal);
  if (directCount !== null) return directCount;

  const fromSeconds = topicTimestampToSeconds(fromTimestamp);
  const toSeconds = topicTimestampToSeconds(toTimestamp);
  if (!Number.isFinite(fromSeconds) || !Number.isFinite(toSeconds) || fromSeconds >= toSeconds) {
    throw new Error("Arquivo.pt result window could not be divided");
  }
  const middle = Math.floor((fromSeconds + toSeconds) / 2);
  const leftCount = await countTopicIntervalExactly(
    query,
    source,
    topicSecondsToTimestamp(fromSeconds),
    topicSecondsToTimestamp(middle),
    signal,
  );
  const rightCount = await countTopicIntervalExactly(
    query,
    source,
    topicSecondsToTimestamp(middle + 1),
    topicSecondsToTimestamp(toSeconds),
    signal,
  );
  return leftCount + rightCount;
}

function topicYearSlices(fromDate, toDate) {
  const fromYear = Number(fromDate.slice(0, 4));
  const toYear = Number(toDate.slice(0, 4));
  return Array.from({ length: toYear - fromYear + 1 }, (_, index) => {
    const year = fromYear + index;
    return {
      year,
      fromDate: fromDate > `${year}-01-01` ? fromDate : `${year}-01-01`,
      toDate: toDate < `${year}-12-31` ? toDate : `${year}-12-31`,
    };
  });
}

async function fetchTopicSeries(query, source, fromDate, toDate, signal, onProgress = null) {
  const slices = topicYearSlices(fromDate, toDate);
  const results = new Array(slices.length);
  let cursor = 0;
  let completed = 0;
  let failed = 0;

  const worker = async () => {
    while (cursor < slices.length) {
      const index = cursor;
      cursor += 1;
      const slice = slices[index];
      try {
        const fromTimestamp = topicApiBoundary(slice.fromDate, false);
        const toTimestamp = topicApiBoundary(slice.toDate, true);
        const count = await countTopicIntervalExactly(query, source, fromTimestamp, toTimestamp, signal);
        results[index] = {
          year: slice.year,
          from_date: slice.fromDate,
          to_date: slice.toDate,
          count,
          failed: false,
        };
      } catch (error) {
        if (signal.aborted) throw error;
        results[index] = {
          year: slice.year,
          from_date: slice.fromDate,
          to_date: slice.toDate,
          count: null,
          failed: true,
          error_code: error?.code || "request_failed",
        };
        failed += 1;
      }
      completed += 1;
      if (onProgress) onProgress(completed, slices.length);
    }
  };

  await Promise.all(Array.from({ length: Math.min(4, slices.length) }, () => worker()));
  if (failed === slices.length) throw new Error("Arquivo.pt unavailable");
  return {
    series: results,
    total: results.reduce((sum, item) => sum + (Number.isFinite(item.count) ? item.count : 0), 0),
    complete: failed === 0,
  };
}

function topicSourceLabel(source) {
  return SOURCE_LABELS[source] || source || t("topicAllSources");
}

function validTopicDate(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(String(value || "")) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
}

function clampTopicDate(value, minimum, maximum) {
  if (!validTopicDate(value)) return minimum;
  if (value < minimum) return minimum;
  if (value > maximum) return maximum;
  return value;
}

function topicSourceMinimumDate(source) {
  const config = state.data?.topic_search || {};
  const globalMinimum = validTopicDate(config.min_date) ? config.min_date : "1996-01-01";
  const sourceMinimum = config.source_metadata?.[source]?.analysis_start;
  return validTopicDate(sourceMinimum) && sourceMinimum > globalMinimum ? sourceMinimum : globalMinimum;
}

function topicSourceMaximumDate(source) {
  const config = state.data?.topic_search || {};
  const globalMaximum = validTopicDate(config.max_date) ? config.max_date : `${new Date().getFullYear()}-12-31`;
  const sourceMaximum = config.source_metadata?.[source]?.analysis_end;
  return validTopicDate(sourceMaximum) && sourceMaximum < globalMaximum ? sourceMaximum : globalMaximum;
}

function topicDateBoundsForAnalyses(analyses) {
  const normalized = analyses.length ? analyses : [normalizedTopicAnalysis({}, 0)];
  const minimum = normalized.reduce((current, analysis) => {
    const candidate = topicSourceMinimumDate(analysis.source);
    return candidate > current ? candidate : current;
  }, topicSourceMinimumDate(""));
  const maximum = normalized.reduce((current, analysis) => {
    const candidate = topicSourceMaximumDate(analysis.source);
    return candidate < current ? candidate : current;
  }, topicSourceMaximumDate(""));
  return { minimum, maximum, hasOverlap: minimum <= maximum };
}

function formatTopicDate(value) {
  if (!validTopicDate(value)) return value;
  return new Intl.DateTimeFormat(state.lang === "pt" ? "pt-PT" : "en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function renderTopicSourceNote() {
  const note = document.getElementById("topic-source-note");
  if (!note) return;
  const analyses = collectTopicAnalysesFromForm();
  const selectedSources = [...new Set(analyses.map((analysis) => analysis.source).filter(Boolean))];
  const bounds = topicDateBoundsForAnalyses(analyses);
  const fastStatus = state.data?.topic_search?.search_status;
  const speedNote = fastStatus?.ready
    ? (state.lang === "pt" ? " Análise rápida indexada disponível." : " Fast indexed analysis is available.")
    : "";
  if (!selectedSources.length) {
    note.textContent = state.lang === "pt"
      ? `Pesquisa no índice preservado do Arquivo.pt entre ${formatTopicDate(bounds.minimum)} e ${formatTopicDate(bounds.maximum)}.${speedNote}`
      : `Searches the preserved Arquivo.pt index between ${formatTopicDate(bounds.minimum)} and ${formatTopicDate(bounds.maximum)}.${speedNote}`;
    return;
  }
  const config = state.data?.topic_search || {};
  const details = selectedSources.map((source) => {
    const createdYear = Number(config.source_metadata?.[source]?.created_year);
    const created = Number.isFinite(createdYear)
      ? (state.lang === "pt" ? `criado em ${createdYear}` : `founded in ${createdYear}`)
      : "";
    const coverage = `${formatTopicDate(topicSourceMinimumDate(source))} – ${formatTopicDate(topicSourceMaximumDate(source))}`;
    return `${topicSourceLabel(source)}${created ? ` (${created})` : ""}: ${coverage}`;
  });
  const prefix = bounds.hasOverlap
    ? (state.lang === "pt" ? "Cobertura preservada no Arquivo.pt" : "Coverage preserved by Arquivo.pt")
    : (state.lang === "pt" ? "As fontes escolhidas não têm um intervalo comum" : "The selected sources have no common date range");
  note.textContent = `${prefix}. ${details.join(" · ")}.${speedNote}`;
}

function applyTopicDateLimits() {
  const fromInput = document.getElementById("topic-from-date");
  const toInput = document.getElementById("topic-to-date");
  if (!fromInput || !toInput) return;
  const analyses = collectTopicAnalysesFromForm();
  const bounds = topicDateBoundsForAnalyses(analyses);
  const minimum = bounds.hasOverlap ? bounds.minimum : bounds.maximum;
  const maximum = bounds.maximum;
  fromInput.min = minimum;
  fromInput.max = maximum;
  toInput.min = minimum;
  toInput.max = maximum;
  let fromDate = clampTopicDate(fromInput.value || state.topicFromDate || minimum, minimum, maximum);
  let toDate = clampTopicDate(toInput.value || state.topicToDate || maximum, minimum, maximum);
  if (fromDate > toDate) toDate = fromDate;
  fromInput.value = fromDate;
  toInput.value = toDate;
  state.topicFromDate = fromDate;
  state.topicToDate = toDate;
  renderTopicSourceNote();
}

function topicSourceOptions(selectedSource = "") {
  const config = state.data?.topic_search || {};
  const sources = Array.isArray(config.sources) ? config.sources : [];
  return [
    `<option value="">${escapeHtml(t("topicAllSources"))}</option>`,
    ...sources.map((source) => {
      const createdYear = Number(config.source_metadata?.[source]?.created_year);
      const suffix = Number.isFinite(createdYear)
        ? (state.lang === "pt" ? ` (criado em ${createdYear})` : ` (founded in ${createdYear})`)
        : "";
      return `<option value="${escapeHtml(source)}"${source === selectedSource ? " selected" : ""}>${escapeHtml(`${topicSourceLabel(source)}${suffix}`)}</option>`;
    }),
  ].join("");
}

function renderTopicAnalysisRows() {
  const container = document.getElementById("topic-analysis-list");
  if (!container) return;
  const analyses = (state.topicAnalyses.length ? state.topicAnalyses : [normalizedTopicAnalysis({}, 0)])
    .slice(0, TOPIC_MAX_ANALYSES)
    .map(normalizedTopicAnalysis);
  state.topicAnalyses = analyses;
  container.innerHTML = analyses.map((analysis, index) => `
    <div class="topic-analysis-row" data-topic-analysis="${index}">
      <label class="topic-query-field">
        <span>${escapeHtml(`${t("topicLabel")} ${index + 1}`)}</span>
        <input data-topic-query type="search" autocomplete="off" value="${escapeHtml(analysis.query)}" ${index === 0 ? "required" : ""}>
      </label>
      <label class="topic-source-field">
        <span>${escapeHtml(t("topicSourceLabel"))}</span>
        <select data-topic-source>${topicSourceOptions(analysis.source)}</select>
      </label>
      <label class="topic-color-field">
        <span>${escapeHtml(t("topicColorLabel"))}</span>
        <input data-topic-color type="color" value="${escapeHtml(analysis.color)}" aria-label="${escapeHtml(`${t("topicColorLabel")} ${index + 1}`)}">
      </label>
      <button type="button" class="topic-remove-analysis" data-remove-analysis="${index}" aria-label="${escapeHtml(t("topicRemoveAnalysis"))}" title="${escapeHtml(t("topicRemoveAnalysis"))}" ${analyses.length === 1 ? "disabled" : ""}>×</button>
    </div>
  `).join("");
  const addButton = document.getElementById("topic-add-analysis");
  if (addButton) {
    const limitReached = analyses.length >= TOPIC_MAX_ANALYSES;
    addButton.disabled = limitReached;
    addButton.hidden = limitReached;
    addButton.setAttribute("aria-label", t("topicAddAnalysis"));
    addButton.title = t("topicAddAnalysis");
  }
}

function renderTopicControls() {
  const fromInput = document.getElementById("topic-from-date");
  const toInput = document.getElementById("topic-to-date");
  const showValues = document.getElementById("topic-show-values");
  if (!fromInput || !toInput || !showValues) return;

  const config = state.data?.topic_search || {};
  const minimum = validTopicDate(config.min_date) ? config.min_date : "1996-01-01";
  const maximum = validTopicDate(config.max_date) ? config.max_date : `${new Date().getFullYear()}-12-31`;
  const params = new URLSearchParams(window.location.search);
  if (!state.topicAnalyses.length) {
    state.topicAnalyses = [normalizedTopicAnalysis({
      query: state.topicQuery || params.get("tema") || "",
      source: state.topicSource || params.get("fonte") || "",
      color: params.get("cor") || TOPIC_DEFAULT_COLORS[0],
    }, 0)];
  }
  if (!state.topicFromDate) state.topicFromDate = validTopicDate(params.get("de")) ? params.get("de") : minimum;
  if (!state.topicToDate) state.topicToDate = validTopicDate(params.get("ate")) ? params.get("ate") : maximum;
  renderTopicAnalysisRows();
  fromInput.value = state.topicFromDate;
  toInput.value = state.topicToDate;
  showValues.checked = state.topicShowValues;
  applyTopicDateLimits();
}

function renderTopicGraph() {
  const container = document.getElementById("topic-results");
  if (!container) return;
  const resultSets = (state.topicResultSets || []).filter((result) => Array.isArray(result.series));
  if (!resultSets.length) {
    container.innerHTML = "";
    return;
  }

  const baseSeries = resultSets[0].series;
  if (!baseSeries.length) {
    container.innerHTML = "";
    return;
  }

  const width = 920;
  const height = 380;
  const left = 62;
  const right = 24;
  const top = 26;
  const bottom = 54;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const verifiedSeries = resultSets.flatMap((result) => result.series).filter((item) => Number.isFinite(item.count));
  const positiveCounts = verifiedSeries.map((item) => item.count).filter((count) => count > 0);
  const maxCount = Math.max(...verifiedSeries.map((item) => item.count), 1);
  const minPositive = positiveCounts.length ? Math.min(...positiveCounts) : 0;
  const useLogScale = minPositive > 0 && maxCount / minPositive >= 100;
  const xForIndex = (index) => left + (baseSeries.length === 1 ? plotWidth / 2 : (index / (baseSeries.length - 1)) * plotWidth);
  const scaledCount = (count) => useLogScale
    ? Math.log1p(Math.max(0, count)) / Math.log1p(maxCount)
    : Math.max(0, count) / maxCount;
  const yForCount = (count) => top + plotHeight - scaledCount(count) * plotHeight;
  const labelStep = Math.max(1, Math.ceil(baseSeries.length / 8));

  const horizontalGrid = Array.from({ length: 5 }, (_, index) => {
    const ratio = index / 4;
    const y = top + plotHeight * ratio;
    const scaledValue = 1 - ratio;
    const value = Math.round(useLogScale
      ? Math.expm1(Math.log1p(maxCount) * scaledValue)
      : maxCount * scaledValue);
    return `<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" class="chart-grid-line"></line><text x="${left - 10}" y="${y + 4}" class="chart-axis-value" text-anchor="end">${escapeHtml(formatMetricNumber(value))}</text>`;
  }).join("");
  const yearLabels = baseSeries.map((item, index) => {
    if (index % labelStep !== 0 && index !== baseSeries.length - 1) return "";
    return `<text x="${xForIndex(index)}" y="${height - 20}" class="chart-year" text-anchor="middle">${item.year}</text>`;
  }).join("");
  const valueOffsets = [-13, 18, -29, 34];
  let postCount = 0;
  const chartSeries = resultSets.map((result, resultIndex) => {
    const color = validTopicColor(result.color, TOPIC_DEFAULT_COLORS[resultIndex]);
    let pathStarted = false;
    const linePath = result.series.map((item, index) => {
      if (!Number.isFinite(item.count)) {
        pathStarted = false;
        return "";
      }
      const command = pathStarted ? "L" : "M";
      pathStarted = true;
      return `${command}${xForIndex(index).toFixed(2)},${yForCount(item.count).toFixed(2)}`;
    }).join(" ");
    const points = result.series.map((item, index) => {
      if (!Number.isFinite(item.count)) return "";
      const x = xForIndex(index);
      const y = yForCount(item.count);
      let labelY = y + valueOffsets[resultIndex];
      if (labelY < top + 10) labelY = y + 17 + (resultIndex * 10);
      if (labelY > top + plotHeight - 2) labelY = y - 13 - (resultIndex * 9);
      const labelX = x + (resultIndex % 2 ? 4 : -4);
      const valueLabel = state.topicShowValues
        ? `<text class="chart-value-label" x="${labelX}" y="${labelY}" text-anchor="middle" style="fill:${color}">${escapeHtml(formatMetricNumber(item.count))}</text>`
        : "";
      return `
        <circle class="chart-point" cx="${x}" cy="${y}" r="4" style="stroke:${color}">
          <title>${escapeHtml(result.query)} · ${item.year}: ${formatMetricNumber(item.count)} ${t("topicMentions")}</title>
        </circle>
        ${valueLabel}
      `;
    }).join("");

    const posts = matchingInstagramPosts(result.query, result.source, state.topicFromDate, state.topicToDate);
    postCount += posts.length;
    const postPoints = posts.map((post, postIndex) => {
      const index = result.series.findIndex((item) => item.year === Number(post.original_year));
      if (index < 0 || !Number.isFinite(result.series[index].count)) return "";
      const y = Math.max(top + 8, yForCount(result.series[index].count) - 15 - ((postIndex % 3) * 11));
      return `<a href="${escapeHtml(newsPageUrl(post))}" data-news-id="${escapeHtml(post.page_id)}"><circle class="chart-post-point" cx="${xForIndex(index)}" cy="${y}" r="5" style="fill:${color}"><title>${escapeHtml(titleWithYear(post))}</title></circle></a>`;
    }).join("");
    return `<path class="chart-line" d="${linePath}" style="stroke:${color}"></path>${points}${postPoints}`;
  }).join("");

  const legend = resultSets.map((result, index) => {
    const color = validTopicColor(result.color, TOPIC_DEFAULT_COLORS[index]);
    return `<span><i style="--series-color:${color}"></i>${escapeHtml(result.query)} · ${escapeHtml(topicSourceLabel(result.source))} · ${escapeHtml(formatMetricNumber(result.total))}</span>`;
  }).join("");
  const chartTitle = resultSets.length === 1 ? resultSets[0].query : t("topicComparisonTitle");
  const verifiedTotal = resultSets.reduce((sum, result) => sum + (Number(result.total) || 0), 0);
  const headingValue = resultSets.length === 1
    ? `${formatMetricNumber(resultSets[0].total)} ${t("topicMentions")}`
    : `${resultSets.length} ${state.lang === "pt" ? "análises" : "analyses"}`;

  container.innerHTML = `
    <div class="topic-result-heading">
      <div>
        <p class="eyebrow">${escapeHtml(resultSets.length === 1 ? topicSourceLabel(resultSets[0].source) : `${resultSets.length} ${state.lang === "pt" ? "análises" : "analyses"}`)}</p>
        <h2>${escapeHtml(chartTitle)}</h2>
      </div>
      <strong>${escapeHtml(headingValue)}</strong>
    </div>
    <div class="topic-series-legend">${legend}</div>
    <div class="topic-chart-shell">
      <svg class="topic-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(`${chartTitle}: ${formatMetricNumber(verifiedTotal)} ${t("topicMentions")}`)}">
        ${horizontalGrid}
        ${chartSeries}
        ${yearLabels}
      </svg>
    </div>
    <div class="topic-chart-footer">
      <div class="topic-chart-notes">
        <span>${escapeHtml(t("topicApiCredit"))}</span>
        <span>${escapeHtml(t("topicCaptureNote"))}</span>
        <span>${escapeHtml(t("topicCoverageUneven"))}</span>
        ${useLogScale ? `<span>${escapeHtml(t("topicLogScale"))}</span>` : ""}
        ${postCount ? `<span class="chart-legend"><i></i>${escapeHtml(t("topicInstagramLegend"))}</span>` : ""}
      </div>
      <div class="chart-download-controls">
        <select id="chart-download-format" aria-label="${escapeHtml(t("topicDownloadFormat"))}">
          <option value="png">PNG</option>
          <option value="svg">SVG</option>
          <option value="csv">CSV</option>
        </select>
        <button type="button" class="chart-download" data-download-chart title="${escapeHtml(t("topicDownload"))}">${escapeHtml(t("topicDownload"))}</button>
      </div>
    </div>
  `;
  const status = document.getElementById("topic-status");
  if (status) {
    const allPeriods = resultSets.flatMap((result) => result.series);
    const failures = allPeriods.filter((item) => item.failed).length;
    const limited = allPeriods.filter((item) => item.error_code === "verification_limit").length;
    if (failures) {
      if (limited) {
        status.textContent = state.lang === "pt"
          ? `${failures} períodos não puderam ser verificados sem tornar a pesquisa excessiva. Escolhe uma fonte ou reduz as datas; estes períodos não foram tratados como zero.`
          : `${failures} periods could not be verified without making the search excessive. Choose a source or shorten the dates; these periods were not treated as zero.`;
      } else {
        status.textContent = state.lang === "pt"
          ? `${failures} períodos não puderam ser verificados e não foram tratados como zero.`
          : `${failures} periods could not be verified and were not treated as zero.`;
      }
    } else {
      status.textContent = verifiedTotal ? "" : t("topicEmpty");
    }
  }
}

function renderTopics() {
  renderTopicControls();
  renderTopicGraph();
}

function safeDownloadPart(value) {
  return normalizedTopicText(value).replace(/\s+/g, "-").slice(0, 48) || "tema";
}

function topicDownloadName(extension) {
  const comparison = (state.topicResultSets || state.topicAnalyses)
    .map((analysis) => safeDownloadPart(analysis.query))
    .filter(Boolean)
    .join("-vs-") || "temas";
  return `noticias-de-ontem-${comparison}-${state.topicFromDate}-${state.topicToDate}.${extension}`;
}

function triggerBlobDownload(blob, extension) {
  const downloadUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = downloadUrl;
  link.download = topicDownloadName(extension);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
}

function csvCell(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function downloadTopicCsv() {
  const collectedAt = new Date().toISOString();
  const portuguese = state.lang === "pt";
  const rows = [
    portuguese
      ? ["analise", "tema", "fonte", "cor", "total_serie", "mostrar_valores", "intervalo_inicio", "intervalo_fim", "ano", "resultados_verificados", "estado", "motivo", "metodo", "url_consulta_arquivo_pt", "consultado_em"]
      : ["analysis", "topic", "source", "colour", "series_total", "show_values", "range_start", "range_end", "year", "verified_results", "status", "reason", "method", "arquivo_pt_query_url", "collected_at"],
    ...(state.topicResultSets || []).flatMap((result, resultIndex) => result.series.map((item) => [
      resultIndex + 1,
      result.query,
      result.source || (portuguese ? "todas" : "all"),
      result.color,
      result.total,
      state.topicShowValues ? (portuguese ? "sim" : "yes") : (portuguese ? "nao" : "no"),
      item.from_date,
      item.to_date,
      item.year,
      Number.isFinite(item.count) ? item.count : "",
      item.failed ? (portuguese ? "nao_verificado" : "not_verified") : (portuguese ? "verificado" : "verified"),
      item.error_code || "",
      item.method || result.method || "paginacao_offset_com_divisao_temporal",
      topicSearchUrl(result.query, result.source, item.from_date, item.to_date),
      collectedAt,
    ])),
  ];
  const csv = `\uFEFF${rows.map((row) => row.map(csvCell).join(",")).join("\r\n")}`;
  triggerBlobDownload(new Blob([csv], { type: "text/csv;charset=utf-8" }), "csv");
}

function exportableTopicSvg(svg) {
  const clone = svg.cloneNode(true);
  const resultSets = state.topicResultSets || [];
  const exportHeight = 452 + (resultSets.length * 24);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("viewBox", `0 0 920 ${exportHeight}`);
  clone.setAttribute("width", "1840");
  clone.setAttribute("height", String(exportHeight * 2));
  const metadata = document.createElementNS("http://www.w3.org/2000/svg", "metadata");
  const methods = [...new Set(resultSets.map((result) => result.method).filter(Boolean))];
  metadata.textContent = JSON.stringify({
    analyses: (state.topicResultSets || []).map((result) => ({
      query: result.query,
      source: result.source || "all",
      color: result.color,
      verified_total: result.total,
    })),
    from_date: state.topicFromDate,
    to_date: state.topicToDate,
    show_values: state.topicShowValues,
    count_methods: methods.length ? methods : ["offset pagination with recursive time splitting"],
    maximum_api_probes: TOPIC_MAX_PROBES_PER_SEARCH,
    data_source: "Arquivo.pt TextSearch API",
    generated_at: new Date().toISOString(),
  });
  clone.insertBefore(metadata, clone.firstChild);
  const style = document.createElementNS("http://www.w3.org/2000/svg", "style");
  style.textContent = `
    .chart-grid-line{stroke:#dbe4ea;stroke-width:1}
    .chart-axis-value,.chart-year{fill:#5c6b78;font-family:Arial,sans-serif;font-size:12px}
    .chart-line{fill:none;stroke:#005a8d;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}
    .chart-point{fill:#fff;stroke:#005a8d;stroke-width:3}
    .chart-post-point{fill:#c44f3b;stroke:#fff;stroke-width:2}
    .chart-value-label{stroke:#fff;stroke-width:4;paint-order:stroke;font-family:Arial,sans-serif;font-size:11px;font-weight:700}
    .export-legend-label{fill:#243746;font-family:Arial,sans-serif;font-size:13px;font-weight:700}
  `;
  clone.insertBefore(style, clone.firstChild);
  const background = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  background.setAttribute("width", "100%");
  background.setAttribute("height", "100%");
  background.setAttribute("fill", "#ffffff");
  clone.insertBefore(background, style.nextSibling);

  const title = document.createElementNS("http://www.w3.org/2000/svg", "text");
  title.setAttribute("x", "62");
  title.setAttribute("y", "402");
  title.setAttribute("fill", "#004b7a");
  title.setAttribute("font-family", "Arial, sans-serif");
  title.setAttribute("font-size", "16");
  title.setAttribute("font-weight", "700");
  title.textContent = `${(state.topicResultSets || []).map((result) => result.query).join(" vs ")} | ${state.topicFromDate} - ${state.topicToDate}`;
  clone.appendChild(title);

  const legend = document.createElementNS("http://www.w3.org/2000/svg", "g");
  legend.setAttribute("data-export-series-legend", "true");
  resultSets.forEach((result, index) => {
    const color = validTopicColor(result.color, TOPIC_DEFAULT_COLORS[index]);
    const y = 426 + (index * 24);
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", "62");
    line.setAttribute("x2", "84");
    line.setAttribute("y1", String(y - 4));
    line.setAttribute("y2", String(y - 4));
    line.setAttribute("stroke", color);
    line.setAttribute("stroke-width", "4");
    legend.appendChild(line);
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", "94");
    label.setAttribute("y", String(y));
    label.setAttribute("class", "export-legend-label");
    label.textContent = `${index + 1}. ${result.query} | ${topicSourceLabel(result.source)} | ${formatMetricNumber(result.total)} ${t("topicMentions")}`;
    legend.appendChild(label);
  });
  clone.appendChild(legend);

  const credit = document.createElementNS("http://www.w3.org/2000/svg", "text");
  credit.setAttribute("x", "62");
  credit.setAttribute("y", String(444 + (resultSets.length * 24)));
  credit.setAttribute("fill", "#5c6b78");
  credit.setAttribute("font-family", "Arial, sans-serif");
  credit.setAttribute("font-size", "12");
  const fastExport = methods.includes("opensearch_fulltext_arquivo_pt");
  credit.textContent = state.lang === "pt"
    ? `Fonte: Arquivo.pt | ${fastExport ? "Indice de texto integral verificado" : "Contagem verificada por paginacao"} | Valores nos pontos: ${state.topicShowValues ? "sim" : "nao"}`
    : `Source: Arquivo.pt | ${fastExport ? "Verified full-text index" : "Count verified by pagination"} | Point values: ${state.topicShowValues ? "yes" : "no"}`;
  clone.appendChild(credit);
  return clone;
}

async function downloadTopicGraph(format = "png") {
  if (format === "csv") {
    downloadTopicCsv();
    return;
  }
  const svg = document.querySelector("#topic-results .topic-chart");
  if (!svg) return;
  const clone = exportableTopicSvg(svg);

  const svgText = new XMLSerializer().serializeToString(clone);
  const blob = new Blob([svgText], { type: "image/svg+xml;charset=utf-8" });
  if (format === "svg") {
    triggerBlobDownload(blob, "svg");
    return;
  }
  const objectUrl = URL.createObjectURL(blob);
  try {
    const image = new Image();
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = reject;
      image.src = objectUrl;
    });
    const canvas = document.createElement("canvas");
    canvas.width = Number(clone.getAttribute("width")) || 1840;
    canvas.height = Number(clone.getAttribute("height")) || 900;
    const context = canvas.getContext("2d");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const pngBlob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png", 0.96));
    if (!pngBlob) return;
    triggerBlobDownload(pngBlob, "png");
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

function loadTopicStateFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const analyses = [];
  for (let index = 0; index < TOPIC_MAX_ANALYSES; index += 1) {
    const suffix = index ? String(index + 1) : "";
    const query = params.get(`tema${suffix}`) || "";
    if (!query && index > 0) continue;
    analyses.push(normalizedTopicAnalysis({
      query,
      source: params.get(`fonte${suffix}`) || "",
      color: params.get(`cor${suffix}`) || TOPIC_DEFAULT_COLORS[index],
    }, index));
  }
  state.topicAnalyses = analyses.length ? analyses : [normalizedTopicAnalysis({}, 0)];
  state.topicQuery = state.topicAnalyses[0].query;
  state.topicSource = state.topicAnalyses[0].source;
  state.topicFromDate = validTopicDate(params.get("de")) ? params.get("de") : "";
  state.topicToDate = validTopicDate(params.get("ate")) ? params.get("ate") : "";
  state.topicShowValues = params.get("valores") !== "0";
  state.topicTotal = 0;
  state.topicSeries = [];
  state.topicResultSets = [];
}

async function runTopicSearch(updateHistory = true) {
  applyTopicDateLimits();
  const analyses = collectTopicAnalysesFromForm().filter((analysis) => analysis.query).slice(0, TOPIC_MAX_ANALYSES);
  let fromDate = document.getElementById("topic-from-date")?.value || "";
  let toDate = document.getElementById("topic-to-date")?.value || "";
  if (!analyses.length || !validTopicDate(fromDate) || !validTopicDate(toDate)) return;
  if (fromDate > toDate) [fromDate, toDate] = [toDate, fromDate];

  state.topicAnalyses = analyses;
  state.topicQuery = analyses[0].query;
  state.topicSource = analyses[0].source;
  state.topicShowValues = document.getElementById("topic-show-values")?.checked !== false;
  state.topicFromDate = fromDate;
  state.topicToDate = toDate;
  state.topicAbort?.abort();
  state.topicAbort = new AbortController();
  const searchAbort = state.topicAbort;
  topicProbeBudgets.set(searchAbort.signal, {
    used: 0,
    maximum: TOPIC_MAX_PROBES_PER_SEARCH * analyses.length,
  });
  state.topicLoading = true;
  state.topicSeries = [];
  state.topicTotal = 0;
  state.topicResultSets = [];
  const submit = document.querySelector("#topic-form button[type='submit']");
  const status = document.getElementById("topic-status");
  const progress = document.getElementById("topic-progress");
  if (submit) submit.disabled = true;
  if (status) status.textContent = "";
  if (progress) progress.hidden = true;
  renderTopicGraph();
  if (updateHistory) {
    history.pushState({}, "", routeUrl("temas", {
      ...topicAnalysisLocationParams(analyses),
      de: fromDate,
      ate: toDate,
      valores: state.topicShowValues ? "1" : "0",
    }));
  }

  const yearsPerAnalysis = topicYearSlices(fromDate, toDate).length;
  const totalPeriods = yearsPerAnalysis * analyses.length;
  let completedPeriods = 0;
  updateTopicProgress(0, totalPeriods);
  try {
    let results;
    if (state.apiBaseUrl) {
      const jobResult = await fetchTopicSeriesFromBackend(
        analyses,
        fromDate,
        toDate,
        state.topicShowValues,
        searchAbort.signal,
      );
      results = analyses.map((analysis, index) => ({
        ...(jobResult.analyses?.[index] || {}),
        ...analysis,
      }));
    } else {
      results = new Array(analyses.length);
      let cursor = 0;
      const worker = async () => {
        while (cursor < analyses.length) {
          const index = cursor;
          cursor += 1;
          const analysis = analyses[index];
          const cacheKey = topicCacheKey(analysis.query, analysis.source, fromDate, toDate);
          const cached = readTopicCache(cacheKey);
          let result = cached;
          if (cached) {
            completedPeriods += cached.series.length;
            updateTopicProgress(completedPeriods, totalPeriods);
          } else {
            try {
              result = await fetchTopicSeries(
                analysis.query,
                analysis.source,
                fromDate,
                toDate,
                searchAbort.signal,
                () => {
                  completedPeriods += 1;
                  updateTopicProgress(completedPeriods, totalPeriods);
                },
              );
            } catch (error) {
              if (searchAbort.signal.aborted) throw error;
              result = {
                series: topicYearSlices(fromDate, toDate).map((slice) => ({
                  year: slice.year,
                  from_date: slice.fromDate,
                  to_date: slice.toDate,
                  count: null,
                  failed: true,
                  error_code: error?.code || "request_failed",
                })),
                total: 0,
                complete: false,
              };
              completedPeriods += yearsPerAnalysis;
              updateTopicProgress(Math.min(completedPeriods, totalPeriods), totalPeriods);
            }
            if (result.complete) writeTopicCache(cacheKey, result);
          }
          results[index] = { ...analysis, ...result };
        }
      };
      await Promise.all(Array.from({ length: Math.min(2, analyses.length) }, () => worker()));
    }
    state.topicResultSets = results;
    state.topicSeries = results[0]?.series || [];
    state.topicTotal = results.reduce((sum, result) => sum + (Number(result.total) || 0), 0);
    renderTopicGraph();
  } catch (error) {
    if (!searchAbort.signal.aborted && status) status.textContent = t("topicError");
  } finally {
    if (state.topicAbort !== searchAbort) return;
    state.topicLoading = false;
    if (submit) submit.disabled = false;
    if (progress) progress.hidden = true;
  }
}

function formatMetricNumber(value) {
  return new Intl.NumberFormat(state.lang === "pt" ? "pt-PT" : "en-GB").format(Math.max(0, Number(value) || 0));
}

function renderMetrics() {
  const container = document.getElementById("metrics-overview");
  if (!container) return;
  const metrics = state.data?.metrics || {};
  const topicSearch = state.data?.topic_search || {};
  const startYear = Number(String(topicSearch.min_date || "").slice(0, 4)) || Number(metrics.coverage_start_year) || 1996;
  const endYear = Number(String(topicSearch.max_date || "").slice(0, 4)) || Number(metrics.coverage_end_year) || new Date().getFullYear();
  const primaryMetric = (value, label, note) => `
    <article class="primary-metric">
      <strong data-counter="${Math.max(0, Number(value) || 0)}">0</strong>
      <h3>${escapeHtml(label)}</h3>
      <p>${escapeHtml(note)}</p>
    </article>
  `;
  const supportingMetric = (value, label, tone) => `
    <div class="supporting-metric supporting-metric-${tone}">
      <strong>${escapeHtml(value)}</strong>
      <span>${escapeHtml(label)}</span>
    </div>
  `;

  container.innerHTML = `
    <div class="metrics-heading">
      <p class="eyebrow">${escapeHtml(t("metricsEyebrow"))}</p>
      <h2 id="metrics-title">${escapeHtml(t("metricsTitle"))}</h2>
    </div>
    <div class="primary-metrics">
      ${primaryMetric(metrics.news_covered, t("metricNews"), t("metricNewsNote"))}
      ${primaryMetric(metrics.published_posts, t("metricPublished"), t("metricPublishedNote"))}
      ${primaryMetric(metrics.social_followers, t("metricFollowers"), t("metricFollowersNote"))}
    </div>
    <div class="supporting-metrics">
      ${supportingMetric(`${startYear}–${endYear}`, t("metricYears"), "news")}
      ${supportingMetric(formatMetricNumber(metrics.unique_sources), t("metricSources"), "followers")}
    </div>
  `;
}

function animateMetricCounters() {
  if (state.counterFrame) window.cancelAnimationFrame(state.counterFrame);
  state.counterRun += 1;
  const run = state.counterRun;
  const overview = document.getElementById("metrics-overview");
  if (overview) overview.dataset.counterRun = String(run);
  const counters = Array.from(document.querySelectorAll("#metrics-overview [data-counter]"));
  if (!counters.length) return;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const targets = counters.map((element) => Math.max(0, Number(element.dataset.counter) || 0));
  const starts = targets.map((target) => {
    if (!target) return 0;
    const highestPower = 10 ** Math.floor(Math.log10(target));
    const animatedPlace = Math.max(1, highestPower / 10);
    const rise = Math.round(animatedPlace * 2.5);
    return Math.max(0, target - rise);
  });
  counters.forEach((element, index) => {
    const target = targets[index];
    const start = starts[index];
    const formatted = formatMetricNumber(target);
    element.textContent = "";
    element.setAttribute("aria-label", formatted);

    if (reduceMotion || target === 0) {
      element.textContent = formatted;
      return;
    }

    const digitCount = Array.from(formatted).filter((character) => /\d/.test(character)).length;
    let digitIndex = 0;
    Array.from(formatted).forEach((character) => {
      if (!/\d/.test(character)) {
        const separator = document.createElement("span");
        separator.className = "odometer-separator";
        separator.setAttribute("aria-hidden", "true");
        separator.textContent = character;
        element.appendChild(separator);
        return;
      }

      const digitsToRight = digitCount - digitIndex - 1;
      const place = 10 ** digitsToRight;
      const actualSteps = Math.floor(target / place) - Math.floor(start / place);
      const startDigit = Math.floor(start / place) % 10;
      const targetDigit = Math.floor(target / place) % 10;
      digitIndex += 1;

      if (actualSteps <= 0) {
        const staticDigit = document.createElement("span");
        staticDigit.className = "odometer-static-digit";
        staticDigit.setAttribute("aria-hidden", "true");
        staticDigit.textContent = String(targetDigit);
        element.appendChild(staticDigit);
        return;
      }

      const maximumSteps = Math.max(10, 20 - (digitsToRight * 2));
      let visibleSteps = actualSteps;
      if (actualSteps > maximumSteps) {
        visibleSteps = actualSteps % 10;
        while (visibleSteps + 10 <= maximumSteps) visibleSteps += 10;
        if (!visibleSteps) visibleSteps = 10;
      }

      const reel = document.createElement("span");
      reel.className = "odometer-digit";
      reel.setAttribute("aria-hidden", "true");

      const track = document.createElement("span");
      track.className = "odometer-track";
      track.style.setProperty("--odometer-shift", `${-(visibleSteps * 1.16)}em`);
      track.style.setProperty("--odometer-delay", `${(index * 55) + (digitsToRight * 16)}ms`);
      for (let step = 0; step <= visibleSteps; step += 1) {
        const digit = document.createElement("span");
        digit.textContent = String((startDigit + step) % 10);
        track.appendChild(digit);
      }
      reel.appendChild(track);
      element.appendChild(reel);
    });
  });

  if (reduceMotion) {
    state.counterFrame = null;
    return;
  }

  state.counterFrame = window.requestAnimationFrame(() => {
    if (run !== state.counterRun || state.route !== "docs") return;
    counters.forEach((element) => element.classList.add("odometer-running"));
    state.counterFrame = null;
  });
}

function renderDocs() {
  const grid = document.getElementById("doc-grid");
  renderMetrics();
  grid.innerHTML = t("docs").map((doc) => `
    <article class="doc-card">
      <h2>${escapeHtml(doc.title)}</h2>
      <p>${escapeHtml(doc.body)}</p>
      <ul>
        ${doc.items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
    </article>
  `).join("");
  const githubLink = document.getElementById("docs-github");
  if (githubLink) githubLink.href = state.data?.github_url || "https://github.com/luisflmaximo/Noticias-de-ontem-pt";
}

function renderStaticText() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    const key = element.getAttribute("data-i18n");
    const value = t(key);
    if (typeof value === "string") element.textContent = value;
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
    element.setAttribute("aria-label", t(element.getAttribute("data-i18n-aria-label")));
  });
  document.querySelectorAll(".language-switch button").forEach((button) => {
    const active = button.dataset.lang === state.lang;
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function render() {
  renderStaticText();
  renderHero();
  renderCarousel();
  renderLatest();
  renderCalendar();
  renderTopics();
  renderDocs();
  renderNewsDetail();
}

function setRoute(route) {
  state.route = route || "home";
  document.body.dataset.route = state.route;
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.dataset.view === state.route);
  });
  document.querySelectorAll(".main-nav a").forEach((link) => {
    link.classList.toggle("active", link.dataset.route === state.route);
  });
  if (state.route === "calendar") {
    renderCalendar();
  }
  if (state.route === "topics") {
    renderTopics();
  }
  if (state.route === "news") {
    renderNewsDetail();
  }
  if (state.route === "docs") {
    renderMetrics();
    animateMetricCounters();
  } else {
    state.counterRun += 1;
    if (state.counterFrame) window.cancelAnimationFrame(state.counterFrame);
    state.counterFrame = null;
  }
  updateDocumentMetadata();
}

function routeFromLocation() {
  const pathname = decodeURIComponent(window.location.pathname).toLowerCase();
  if (pathname.match(/\/(calendário|calendario)(?:\/\d{4}-\d{2}-\d{2})?\/?$/)) return "calendar";
  if (pathname.match(/\/temas\/?$/)) return "topics";
  if (pathname.match(/\/(documentação|documentacao)\/?$/)) return "docs";
  if (pathname.match(/\/noticia(?:\/[^/]+)?\/?$/)) return "news";
  return "home";
}

function startCarousel() {
  const moveTo = (index) => {
    const items = state.data?.carousel || [];
    if (!items.length) return;
    state.slide = (index + items.length) % items.length;
    renderHero();
  };
  const next = () => moveTo(state.slide + 1);
  clearInterval(state.timer);
  state.timer = setInterval(next, 5200);
  document.getElementById("hero-next-slide")?.addEventListener("click", next);
  document.getElementById("hero-prev-slide")?.addEventListener("click", () => moveTo(state.slide - 1));
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function wireLanguageSwitch() {
  document.querySelectorAll(".language-switch button").forEach((button) => {
    button.addEventListener("click", () => {
      const nextLang = button.dataset.lang;
      if (nextLang === state.lang) return;
      state.lang = nextLang;
      localStorage.setItem("ndo-lang", state.lang);
      document.body.classList.add("switching");
      window.setTimeout(() => {
        render();
        setRoute(state.route);
        document.body.classList.remove("switching");
      }, 120);
    });
  });
}

function wireNavigation() {
  const homeLink = document.querySelector("[data-home-link]");
  if (homeLink) {
    homeLink.href = routeUrl("inicio");
    homeLink.addEventListener("click", (event) => {
      event.preventDefault();
      history.pushState({}, "", routeUrl("inicio"));
      setRoute("home");
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  document.querySelectorAll(".main-nav a").forEach((link) => {
    const path = link.dataset.path || "inicio";
    link.href = routeUrl(path);
    link.addEventListener("click", (event) => {
      event.preventDefault();
      history.pushState({}, "", routeUrl(path));
      const route = routeFromLocation();
      if (route === "calendar") {
        state.calendarPickerVisible = true;
        state.calendarSource = "";
      }
      setRoute(route);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
  window.addEventListener("popstate", () => {
    state.selectedDate = selectedDateFromLocation() || state.selectedDate;
    const route = routeFromLocation();
    if (route === "calendar") state.calendarPickerVisible = !selectedDateFromLocation();
    if (route === "topics") loadTopicStateFromLocation();
    setRoute(route);
    if (route === "topics" && state.topicQuery) runTopicSearch(false);
  });
}

function wireStoryLinks() {
  document.getElementById("main")?.addEventListener("click", (event) => {
    const link = event.target.closest("[data-news-id]");
    if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const pageId = link.dataset.newsId;
    if (!pageId) return;
    event.preventDefault();
    history.pushState({}, "", newsPageUrl({ page_id: pageId }));
    setRoute("news");
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

function wireTopics() {
  document.getElementById("topic-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    runTopicSearch(true);
  });
  document.getElementById("topic-add-analysis")?.addEventListener("click", () => {
    state.topicAnalyses = collectTopicAnalysesFromForm();
    if (state.topicAnalyses.length >= TOPIC_MAX_ANALYSES) return;
    state.topicAnalyses.push(normalizedTopicAnalysis({}, state.topicAnalyses.length));
    renderTopicAnalysisRows();
    applyTopicDateLimits();
  });
  document.getElementById("topic-analysis-list")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-analysis]");
    if (!button) return;
    const index = Number(button.dataset.removeAnalysis);
    const analyses = collectTopicAnalysesFromForm();
    if (!Number.isInteger(index) || analyses.length <= 1) return;
    analyses.splice(index, 1);
    state.topicAnalyses = analyses.map(normalizedTopicAnalysis);
    renderTopicAnalysisRows();
    applyTopicDateLimits();
  });
  document.getElementById("topic-analysis-list")?.addEventListener("change", (event) => {
    state.topicAnalyses = collectTopicAnalysesFromForm();
    if (event.target.matches("[data-topic-source]")) applyTopicDateLimits();
  });
  document.getElementById("topic-analysis-list")?.addEventListener("input", (event) => {
    state.topicAnalyses = collectTopicAnalysesFromForm();
    if (!event.target.matches("[data-topic-color]")) return;
    const row = event.target.closest("[data-topic-analysis]");
    const index = Number(row?.dataset.topicAnalysis);
    if (Number.isInteger(index) && state.topicResultSets[index]) {
      state.topicResultSets[index].color = state.topicAnalyses[index].color;
      renderTopicGraph();
    }
  });
  ["topic-from-date", "topic-to-date"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", applyTopicDateLimits);
  });
  document.getElementById("topic-show-values")?.addEventListener("change", (event) => {
    state.topicShowValues = event.target.checked;
    renderTopicGraph();
  });
  document.getElementById("topic-results")?.addEventListener("click", (event) => {
    if (!event.target.closest("[data-download-chart]")) return;
    const format = document.getElementById("chart-download-format")?.value || "png";
    downloadTopicGraph(format);
  });
}

function wireCalendar() {
  const selectCalendarDate = (dateValue) => {
    if (!isValidIsoDate(dateValue)) return;
    state.selectedDate = dateValue;
    state.calendarYear = dateYear(dateValue);
    state.calendarMonth = Number(dateValue.slice(5, 7));
    state.calendarSource = "";
    state.calendarPickerVisible = false;
    history.pushState({}, "", routeUrl("calendario", { data: dateValue }));
    setRoute("calendar");
  };

  const shiftDay = (delta) => {
    const [year, month, day] = state.selectedDate.split("-").map(Number);
    const date = new Date(year, month - 1, day + delta);
    selectCalendarDate(isoDate(date.getFullYear(), date.getMonth() + 1, date.getDate()));
  };

  document.getElementById("calendar-grid")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-date]");
    if (!button) return;
    selectCalendarDate(button.dataset.date);
  });

  document.getElementById("calendar-year")?.addEventListener("change", (event) => {
    const year = Number(event.target.value);
    if (!Number.isFinite(year)) return;
    state.calendarYear = Math.min(Math.max(Math.trunc(year), 1996), 2050);
    renderCalendarGrid();
  });

  document.getElementById("calendar-month")?.addEventListener("change", (event) => {
    const month = Number(event.target.value);
    if (!Number.isFinite(month)) return;
    state.calendarMonth = Math.min(Math.max(Math.trunc(month), 1), 12);
    renderCalendarGrid();
  });

  const shiftMonth = (delta) => {
    const date = new Date(state.calendarYear, state.calendarMonth - 1 + delta, 1);
    state.calendarYear = date.getFullYear();
    state.calendarMonth = date.getMonth() + 1;
    renderCalendarGrid();
  };
  document.getElementById("calendar-prev-month")?.addEventListener("click", () => shiftMonth(-1));
  document.getElementById("calendar-next-month")?.addEventListener("click", () => shiftMonth(1));
  document.getElementById("calendar-prev-day")?.addEventListener("click", () => shiftDay(-1));
  document.getElementById("calendar-next-day")?.addEventListener("click", () => shiftDay(1));
  document.getElementById("calendar-date-picker")?.addEventListener("change", (event) => {
    selectCalendarDate(event.target.value);
  });
  document.getElementById("calendar-source")?.addEventListener("change", (event) => {
    state.calendarSource = event.target.value;
    renderDayPanel();
    loadCalendarRecommendations();
  });
}

async function init() {
  wireNavigation();
  wireCalendar();
  wireLanguageSwitch();
  wireStoryLinks();
  wireTopics();
  try {
    const response = await fetch(assetPath("data/news.json"), { cache: "no-store" });
    state.data = await response.json();
  } catch {
    state.data = { featured: null, carousel: [], latest: [], metrics: {}, has_published_posts: false };
  }
  await loadDynamicRuntimeData();
  const initialRoute = routeFromLocation();
  if (initialRoute === "topics") loadTopicStateFromLocation();
  render();
  setRoute(initialRoute);
  if (initialRoute === "topics" && state.topicQuery) runTopicSearch(false);
  startCarousel();
}

init();
