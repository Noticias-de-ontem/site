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
  calendarFormat: "month",
  calendarView: "onthisday",
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
  topicGranularity: "year",
  topicFromDate: "",
  topicToDate: "",
  topicTotal: 0,
  topicSeries: [],
  topicLoading: false,
  topicAbort: null,
  apiBaseUrl: "",
};

// Máximo de publicações do projeto no topo de qualquer período do calendário.
const CALENDAR_POSTS_LIMIT = 6;

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

// Níveis de relevância histórica — nomes e resumos por idioma (ver
// historical_relevance.py no gerador).
const RELEVANCE_LEVELS = {
  pt: [
    { level: 1, name: "Marco Histórico", tooltip: "Acontecimento que mudou o rumo da História, com consequências estruturais e duradouras." },
    { level: 2, name: "Grande Relevância", tooltip: "Grande impacto nacional ou internacional, sem ser necessariamente um ponto de viragem histórico." },
    { level: 3, name: "Relevância Regional", tooltip: "Importância especialmente forte para uma região, país ou comunidade." },
    { level: 4, name: "Interesse Público", tooltip: "Grande atenção pública na época, com impacto histórico de longo prazo limitado." },
    { level: 5, name: "Contexto Histórico", tooltip: "Não foi determinante por si, mas ajuda a compreender a época e outros acontecimentos." },
  ],
  en: [
    { level: 1, name: "Historic Landmark", tooltip: "An event that changed the course of history, with lasting, structural consequences." },
    { level: 2, name: "Major Event", tooltip: "Major national or international impact, though not necessarily a turning point." },
    { level: 3, name: "Regional Relevance", tooltip: "Especially significant for a specific region, country, or community." },
    { level: 4, name: "Public Interest", tooltip: "Drew major public attention at the time, with limited long-term historical impact." },
    { level: 5, name: "Historical Context", tooltip: "Not decisive on its own, but useful for understanding the era and later events." },
  ],
};

// Ícones vetoriais por nível (coroa, estrela, pessoas, jornal, lupa).
const RELEVANCE_ICONS = {
  1: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 8l4 4 5-6 5 6 4-4v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8z"/></svg>',
  2: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2l2.9 6.3 6.9.8-5.1 4.7 1.4 6.8L12 17.2 5.9 20.6l1.4-6.8L2.2 9.1l6.9-.8L12 2z"/></svg>',
  3: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm7 1a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM2.5 18c0-2.6 2.9-4.5 6.5-4.5s6.5 1.9 6.5 4.5v1h-13v-1zm15.5 1v-1c0-1.5-.6-2.8-1.7-3.8 2.9.3 5.2 1.9 5.2 3.8v1h-3.5z"/></svg>',
  4: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h13a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5zm2 4h4v4H6V9zm6 0h5v1.5h-5V9zm0 3.5h5V14h-5v-1.5zM6 15h11v1.5H6V15z"/></svg>',
  5: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10.5 3a7.5 7.5 0 0 1 5.9 12.1l4.3 4.3-1.4 1.4-4.3-4.3A7.5 7.5 0 1 1 10.5 3zm0 2a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11z"/></svg>',
};

// Redes sociais: ícones, etiquetas e URL padrão enquanto não existem
// publicações reais (os links ativos chegam via network_posts do publisher).
const SOCIAL_NETWORKS = {
  instagram: {
    label: "Instagram",
    url: "https://www.instagram.com/",
    icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.2c3.2 0 3.6 0 4.9.1 1.2.1 1.8.2 2.2.4.6.2 1 .5 1.4.9.4.4.7.8.9 1.4.2.4.4 1 .4 2.2.1 1.3.1 1.7.1 4.9s0 3.6-.1 4.9c-.1 1.2-.2 1.8-.4 2.2-.2.6-.5 1-.9 1.4-.4.4-.8.7-1.4.9-.4.2-1 .4-2.2.4-1.3.1-1.7.1-4.9.1s-3.6 0-4.9-.1c-1.2-.1-1.8-.2-2.2-.4-.6-.2-1-.5-1.4-.9-.4-.4-.7-.8-.9-1.4-.2-.4-.4-1-.4-2.2C2.2 15.6 2.2 15.2 2.2 12s0-3.6.1-4.9c.1-1.2.2-1.8.4-2.2.2-.6.5-1 .9-1.4.4-.4.8-.7 1.4-.9.4-.2 1-.4 2.2-.4C8.4 2.2 8.8 2.2 12 2.2zm0 2.9a6.9 6.9 0 1 0 0 13.8 6.9 6.9 0 0 0 0-13.8zm0 11.4a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9zm7.2-11.7a1.6 1.6 0 1 1-3.2 0 1.6 1.6 0 0 1 3.2 0z"/></svg>',
  },
  facebook: {
    label: "Facebook",
    url: "https://www.facebook.com/",
    icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13.5 21v-7.8h2.6l.4-3h-3V8.3c0-.9.2-1.5 1.5-1.5h1.6V4.1c-.3 0-1.2-.1-2.3-.1-2.3 0-3.9 1.4-3.9 4v2.2H7.8v3h2.6V21h3.1z"/></svg>',
  },
  x: {
    label: "X",
    url: "https://x.com/",
    icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17.8 3h3l-6.6 7.6L22 21h-6.1l-4.8-6.3L5.6 21h-3l7.1-8.1L2 3h6.3l4.3 5.7L17.8 3zm-1.1 16.2h1.7L7.4 4.7H5.6l11.1 14.5z"/></svg>',
  },
};

// Badge da rede com link para a publicação (ou URL padrão em testes).
function networkBadgesHtml(item) {
  const networks = Array.isArray(item?.networks) ? item.networks : [];
  if (!networks.length) return "";
  return networks.map((network) => {
    const meta = SOCIAL_NETWORKS[network];
    if (!meta) return "";
    const href = item?.network_posts?.[network] || meta.url;
    return `<a class="network-badge network-${network}" href="${escapeHtml(href)}" target="_blank" rel="noreferrer" title="${escapeHtml(meta.label)}">${meta.icon}<span>${escapeHtml(meta.label)}</span></a>`;
  }).join("");
}

const SOURCE_TYPE_KEY = {
  newspaper: "sourceTypeNewspaper",
  internet_profile: "sourceTypeProfile",
  wikipedia: "sourceTypeWikipedia",
  archive: "sourceTypeArchive",
};

function relevanceLevelInfo(item) {
  const level = Number(item && item.relevance_level);
  if (!level || level < 1 || level > 5) return null;
  const table = RELEVANCE_LEVELS[state.lang === "en" ? "en" : "pt"] || RELEVANCE_LEVELS.pt;
  return table.find((entry) => entry.level === level) || null;
}

function relevanceBadge(item, options = {}) {
  const info = relevanceLevelInfo(item);
  if (!info) return "";
  const aria = t("relevanceHelpAria");
  const icon = RELEVANCE_ICONS[info.level] || "";
  const size = options.compact ? " relevance-badge-compact" : "";
  return (
    `<span class="relevance-badge relevance-level-${info.level}${size}" data-relevance-level="${info.level}" ` +
    `tabindex="0" role="button" aria-describedby="relevance-tooltip" aria-label="${aria}">` +
    `${icon}<span class="relevance-badge-name">${info.name}</span></span>`
  );
}

function sourceTypeChip(item) {
  const type = item && item.source_type ? item.source_type : "archive";
  const key = SOURCE_TYPE_KEY[type] || SOURCE_TYPE_KEY.archive;
  return `<span class="source-chip source-${type}">${t(key)}</span>`;
}


const i18n = {
  pt: {
    navHome: "Início",
    navCalendar: "Calendário",
    navTopics: "Temas",
    navDocs: "Documentação",
    heroEyebrow: "Notícia principal",
    heroEyebrowWeek: "Notícia da semana",
    heroEyebrowDay: "Notícia do dia",
    heroEyebrowFeatured: "Notícia em destaque",
    carouselEyebrow: "Seleção editorial",
    carouselTitle: "Histórias em destaque",
    heroPreviousSlide: "Destaque anterior",
    heroNextSlide: "Destaque seguinte",
    exploreTitle: "Explorar o projeto",
    exploreCalendarTitle: "Explorar por data",
    exploreCalendarBody: "Notícias do mesmo dia em vários anos, preservadas pelo Arquivo.pt.",
    exploreTopicsTitle: "Evolução de temas",
    exploreTopicsBody: "Compara a presença de um assunto no índice preservado, ano a ano.",
    exploreDocsTitle: "Como funciona",
    exploreDocsBody: "O método, as fontes e a cobertura do projeto, em números.",
    footerInstagram: "Instagram",
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
    monthRecommendationsTitle: "Notícias importantes de",
    openDay: "Abrir dia",
    calendarFormatLabel: "Formato",
    calendarFormatMonth: "Mês",
    calendarFormatWeek: "Semana",
    calendarViewLabel: "Vista",
    calendarViewOnThisDay: "Notícias de Ontem",
    calendarViewExactDate: "Dia exato",
    calendarWeekPrevious: "Semana anterior",
    calendarWeekNext: "Semana seguinte",
    weekRangeJoin: "a",
    exactDayTitle: "Notícias de",
    projectPostsTitle: "Publicações do projeto",
    noPostsForPeriod: "Sem publicações do projeto neste período.",
    relevanceWhy: "Porquê este nível?",
    relevanceHelpAria: "O que significa este nível de relevância",
    sourceTypeNewspaper: "Jornal",
    sourceTypeProfile: "Perfil da internet",
    sourceTypeWikipedia: "Wikipédia",
    sourceTypeArchive: "Arquivo.pt",
    scoreImpact: "Impacto histórico",
    scoreScope: "Dimensão do impacto",
    scoreConsequences: "Consequências",
    scoreLater: "Relevância posterior",
    scoreDuration: "Dimensão e duração",
    scoreMedia: "Relevância mediática",
    scoreUniqueness: "Singularidade",
    relevanceDefaultNote: "Classificação provisória: pontuação detalhada ainda não calculada para esta notícia.",
    relevanceEyebrow: "Níveis de relevância histórica",
    relevanceDocTitle: "Como distinguimos a relevância das notícias",
    relevanceDocLead: "Cada notícia recebe um badge que indica o seu grau de importância histórica. O nível resulta de uma pontuação objetiva — e não de uma opinião solta da inteligência artificial.",
    relevanceDocHow: "Como o nível é atribuído",
    relevanceDocHowBody: "Cada critério recebe uma nota de 0 a 100. A pontuação final é a média ponderada dos sete critérios e é ela que define o nível: 85 ou mais é Marco Histórico, 70 a 84 é Grande Relevância, 55 a 69 é Relevância Regional, 40 a 54 é Interesse Público e abaixo de 40 é Contexto Histórico. A inteligência artificial propõe as notas, mas o nível é sempre recalculado pelo sistema a partir delas.",
    relevanceDocMedia: "Relevância mediática não é importância histórica",
    relevanceDocMediaBody: "Uma notícia pode ter sido extremamente popular durante uma semana e hoje ter pouca importância histórica. O contrário também acontece. Por isso, a relevância mediática pesa apenas 5% e nunca determina o nível sozinha.",
    relevanceDocLandmark: "Regra do Marco Histórico",
    relevanceDocLandmarkBody: "Uma notícia nunca recebe Marco Histórico só porque a IA a considera importante. Para esse nível exige-se pontuação mínima de 90 nos quatro critérios substantivos e uma justificação explícita das consequências posteriores do acontecimento.",
    relevanceDocCuration: "Os badges como curadoria",
    relevanceDocCurationBody: "Os destaques do site — notícia principal e carrossel — são escolhidos apenas entre notícias de Marco Histórico ou Grande Relevância. No calendário, as publicações do projeto aparecem primeiro (até seis por período, por nível de badge), seguidas das restantes notícias ordenadas da mesma forma.",
    relevanceDocCriteriaTitle: "Critérios de atribuição",
    relevanceDocExampleTitle: "Exemplo de uma notícia",
    relevanceDocExampleBadge: "Marco Histórico",
    relevanceDocExampleHeadline: "25 de Abril de 1974: o fim da ditadura e o início da democracia em Portugal",
    relevanceDocExampleBody: "A revolução dos cravos é um acontecimento fundamental na história de Portugal e da Europa, com impacto político, social e cultural duradouro — pontuações altas em impacto, consequências e relevância posterior.",
    relevanceDocScoresNote: "No site, a pontuação completa de cada notícia aparece na respetiva página individual.",
    homeHighlightsEyebrow: "Agora no projeto",
    homeHighlightsTitle: "Destaques",
    homeLevel1Title: "Marcos Históricos",
    homeLevel1Lead: "Acontecimentos que mudaram o rumo da História.",
    homeLevel2Title: "Grande Relevância",
    homeLevel2Lead: "Momentos decisivos de grande impacto nacional ou internacional.",
    homeMoreTitle: "Mais notícias",
    homeMoreLead: "Notícias de interesse público e contexto histórico para compreender a época.",
    sameDayTitle: "No mesmo dia",
    sameDayLead: "Outros acontecimentos preservados nesta data, em anos diferentes.",
    previousStory: "Notícia anterior",
    nextStory: "Notícia seguinte",
    breadcrumbHome: "Início",
    breadcrumbCalendar: "Calendário",
    footerSourcesTitle: "Fontes acompanhadas",
    footerExploreTitle: "Explorar",
    footerAboutTitle: "Sobre o projeto",
    footerBackTop: "Voltar ao topo",
    minuteFeedTitle: "Arquivo ao minuto",
    minuteFeedLead: "As últimas publicações do nosso perfil.",
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
    topicAllSources: "Todas as fontes disponíveis",
    topicApiCredit: "Contagem verificada nos resultados indexados pelo Arquivo.pt.",
    topicLoadingNote: "Pode demorar devido ao grande volume de conteúdos analisados. Para pesquisas muito amplas, escolhe uma fonte ou reduz o intervalo.",
    topicCoverageUneven: "A cobertura da pesquisa varia conforme o ano e a fonte; zero significa que o índice não devolveu resultados nesse período.",
    topicLogScale: "Escala logarítmica para tornar visíveis anos com menos resultados.",
    topicCaptureNote: "Cada valor conta registos arquivados que correspondem à pesquisa. A mesma página pode ter sido arquivada mais de uma vez.",
    topicMentions: "resultados verificados",
    topicInstagramLegend: "Publicação no Instagram",
    topicDownload: "Descarregar gráfico",
    topicDownloadFormat: "Formato de descarga",
    topicGranularityLabel: "Períodos",
    topicGranularityYear: "Por ano",
    topicGranularityMonth: "Por mês",
    topicGranularityDay: "Por dia",
    topicGranularityMonthTip: "A verificação por mês só está disponível para períodos de 2 anos ou menos: cada mês é verificado ponto a ponto e períodos longos tornariam a pesquisa excessiva.",
    topicGranularityDayTip: "A verificação por dia está disponível para um mês completo (ou janelas equivalentes, como de 17 de agosto a 17 de setembro): cada dia é verificado individualmente.",
    topicGranularityLocked: "Escolhe um período mais curto para desbloquear.",
    topicFailedPoint: "Não verificado (falha na consulta)",
    topicMonthDivider: "mudança de mês",
    topicEmpty: "Não foram encontrados resultados neste intervalo.",
    topicError: "Não foi possível concluir a pesquisa no Arquivo.pt. Tenta novamente dentro de momentos.",
    newsEyebrow: "Notícia preservada",
    newsOpenArquivo: "Abrir notícia no Arquivo.pt",
    newsOpenInstagram: "Abrir publicação no Instagram",
    newsNotFound: "Notícia não encontrada",
    newsNotFoundBody: "Este endereço já não corresponde a uma notícia disponível.",
    newsBack: "Voltar ao calendário",
    publishedOn: "Publicado a",
    originalYearLabel: "Notícia original de",
    snapshotCaption: "Página original preservada no Arquivo.pt",
    snapshotSectionTitle: "A página preservada",
    snapshotCaptured: "Captura de",
    viewOriginal: "Ver página original",
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
    heroEyebrowWeek: "Story of the week",
    heroEyebrowDay: "Today’s story",
    heroEyebrowFeatured: "Featured story",
    carouselEyebrow: "Editorial selection",
    carouselTitle: "Featured stories",
    heroPreviousSlide: "Previous highlight",
    heroNextSlide: "Next highlight",
    exploreTitle: "Explore the project",
    exploreCalendarTitle: "Explore by date",
    exploreCalendarBody: "News from the same day across the years, preserved by Arquivo.pt.",
    exploreTopicsTitle: "Topic evolution",
    exploreTopicsBody: "Compare how a subject appears in the preserved index, year by year.",
    exploreDocsTitle: "How it works",
    exploreDocsBody: "The method, the sources and the project's coverage, in numbers.",
    footerInstagram: "Instagram",
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
    monthRecommendationsTitle: "Important stories from",
    openDay: "Open day",
    calendarFormatLabel: "Layout",
    calendarFormatMonth: "Month",
    calendarFormatWeek: "Week",
    calendarViewLabel: "View",
    calendarViewOnThisDay: "On this day",
    calendarViewExactDate: "Exact date",
    calendarWeekPrevious: "Previous week",
    calendarWeekNext: "Next week",
    weekRangeJoin: "to",
    exactDayTitle: "Stories from",
    projectPostsTitle: "Project posts",
    noPostsForPeriod: "No project posts for this period yet.",
    relevanceWhy: "Why this level?",
    relevanceHelpAria: "What this relevance level means",
    sourceTypeNewspaper: "Newspaper",
    sourceTypeProfile: "Internet profile",
    sourceTypeWikipedia: "Wikipedia",
    sourceTypeArchive: "Arquivo.pt",
    scoreImpact: "Historical impact",
    scoreScope: "Scope of impact",
    scoreConsequences: "Consequences",
    scoreLater: "Influence on later events",
    scoreDuration: "Scale and duration",
    scoreMedia: "Media attention",
    scoreUniqueness: "Uniqueness",
    relevanceDefaultNote: "Provisional rating: detailed scores for this story haven't been computed yet.",
    relevanceEyebrow: "Historical relevance levels",
    relevanceDocTitle: "How we measure a story's relevance",
    relevanceDocLead: "Every story gets a badge indicating its historical weight. The level comes from an objective score — never from a free-form opinion by the AI.",
    relevanceDocHow: "How the level is assigned",
    relevanceDocHowBody: "Each criterion receives a 0-100 score. The final score is the weighted average of all seven criteria, and that number sets the level: 85 or above is a Historic Landmark, 70-84 a Major Event, 55-69 Regional Relevance, 40-54 Public Interest, and below 40 Historical Context. The AI proposes the scores, but the system always recomputes the level from them.",
    relevanceDocMedia: "Media attention is not historical importance",
    relevanceDocMediaBody: "A story can be hugely popular for a week and still matter little to history — and the reverse happens too. That's why media attention only weighs 5% and can never set the level on its own.",
    relevanceDocLandmark: "The Historic Landmark rule",
    relevanceDocLandmarkBody: "A story never becomes a Historic Landmark just because the AI finds it important. That level requires at least 90 points on each of the four substantive criteria plus an explicit account of the event's later consequences.",
    relevanceDocCuration: "Badges as curation",
    relevanceDocCurationBody: "The site's highlights — the lead story and the carousel — are chosen only among Historic Landmarks and Major Events. In the calendar, project posts come first (up to six per period, ordered by badge), followed by the remaining stories sorted the same way.",
    relevanceDocCriteriaTitle: "Scoring criteria",
    relevanceDocExampleTitle: "A worked example",
    relevanceDocExampleBadge: "Historic Landmark",
    relevanceDocExampleHeadline: "April 25, 1974: the end of the dictatorship and the beginning of democracy in Portugal",
    relevanceDocExampleBody: "The Carnation Revolution is a foundational event in Portuguese and European history, with lasting political, social, and cultural impact — top scores in impact, consequences, and influence on later events.",
    relevanceDocScoresNote: "On the site, each story's full score breakdown appears on its own page.",
    homeHighlightsEyebrow: "Now on the project",
    homeHighlightsTitle: "Top stories",
    homeLevel1Title: "Historic Landmarks",
    homeLevel1Lead: "Events that changed the course of history.",
    homeLevel2Title: "Major Events",
    homeLevel2Lead: "Decisive moments with major national or international impact.",
    homeMoreTitle: "More stories",
    homeMoreLead: "Stories of public interest and historical context to understand the era.",
    sameDayTitle: "On the same day",
    sameDayLead: "Other preserved events from this date, in different years.",
    previousStory: "Previous story",
    nextStory: "Next story",
    breadcrumbHome: "Home",
    breadcrumbCalendar: "Calendar",
    footerSourcesTitle: "Sources we follow",
    footerExploreTitle: "Explore",
    footerAboutTitle: "About the project",
    footerBackTop: "Back to top",
    minuteFeedTitle: "Archive live feed",
    minuteFeedLead: "The latest posts from our profile.",
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
    topicAllSources: "All available sources",
    topicApiCredit: "Count verified against results indexed by Arquivo.pt.",
    topicLoadingNote: "This may take a while because of the large volume being analysed. For very broad searches, choose a source or shorten the range.",
    topicCoverageUneven: "Search coverage varies by year and source; zero means the index returned no results for that period.",
    topicLogScale: "Logarithmic scale used to keep years with fewer results visible.",
    topicCaptureNote: "Each value counts archived records matching the query. The same page may have been archived more than once.",
    topicMentions: "verified results",
    topicInstagramLegend: "Instagram post",
    topicDownload: "Download chart",
    topicDownloadFormat: "Download format",
    topicGranularityLabel: "Periods",
    topicGranularityYear: "Yearly",
    topicGranularityMonth: "Monthly",
    topicGranularityDay: "Daily",
    topicGranularityMonthTip: "Monthly verification is only available for periods of 2 years or less: each month is verified point by point, and longer periods would make the search excessive.",
    topicGranularityDayTip: "Daily verification is available for a full month (or equivalent windows, such as August 17 to September 17): each day is verified individually.",
    topicGranularityLocked: "Choose a shorter period to unlock.",
    topicFailedPoint: "Not verified (query failed)",
    topicMonthDivider: "month change",
    topicEmpty: "No results were found in this time range.",
    topicError: "The Arquivo.pt search could not be completed. Please try again shortly.",
    newsEyebrow: "Preserved story",
    newsOpenArquivo: "Open story on Arquivo.pt",
    newsOpenInstagram: "Open Instagram post",
    newsNotFound: "Story not found",
    newsNotFoundBody: "This address no longer matches an available story.",
    newsBack: "Back to the calendar",
    publishedOn: "Published on",
    originalYearLabel: "Original story from",
    snapshotCaption: "Original page preserved by Arquivo.pt",
    snapshotSectionTitle: "The preserved page",
    snapshotCaptured: "Captured on",
    viewOriginal: "View original page",
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
  return new Intl.DateTimeFormat(state.lang === "pt" ? "pt-PT" : "en-US", {
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
  // A grelha do mês fica sempre visível: é a forma mais simples de navegar.
  state.calendarPickerVisible = true;
}

function monthName(monthIndex) {
  const date = new Date(2026, monthIndex, 1);
  return new Intl.DateTimeFormat(state.lang === "pt" ? "pt-PT" : "en-US", { month: "long" }).format(date);
}

// Categorias: em EN apresentam-se traduzidas (os dados ficam em PT).
const CATEGORY_EN = {
  "POLÍTICA": "POLITICS",
  "POLITICA": "POLITICS",
  "DESPORTO": "SPORTS",
  "CULTURA": "CULTURE",
  "SOCIEDADE": "SOCIETY",
  "CIÊNCIA": "SCIENCE",
  "CIENCIA": "SCIENCE",
  "NACIONAL": "NATIONAL",
  "MUNDIAL": "WORLD",
  "ESTRELA": "STARS",
  "CURIOSO": "OFFBEAT",
  "ECONOMIA": "ECONOMY",
  "ATUALIDADE": "NEWS",
};

function itemMeta(item) {
  if (!item.category) return [];
  const category = state.lang === "en" ? CATEGORY_EN[item.category] || item.category : item.category;
  return [category];
}

// Título limpo (sem ano residual) para contexts onde o ano aparece à parte.
function cleanTitle(item) {
  const title = localized(item, "title");
  if (!title) return "";
  const year = String(item?.original_year || "").trim();
  if (!year) return title.replace(/[,\s]+$/, "").trim();
  const pattern = new RegExp(`[\\s,;:.]*\\(?${t("yearOnly")}\\s*\\)?\\s*${year}\\s*[.,;:!?]*$`, "i");
  return title.replace(pattern, "").replace(/[,\s]+$/, "").trim() || title;
}

// Títulos nunca terminam em vírgula nem levam o ano embutido — o ano
// aparece à parte (pílula pequena no hero, linha de datas nas páginas).
function titleWithYear(item) {
  return cleanTitle(item);
}

// Título para o banner/hero: sem pontos de interrogação (mais texto cabe
// reduzindo o tamanho da letra, nunca cortando a frase com "?").
function bannerTitle(item) {
  return cleanTitle(item).replace(/\s*\?+\s*/g, " ").replace(/\s{2,}/g, " ").trim();
}

function newsPageUrl(item) {
  // URL limpo estilo jornal (noticia/AAAA/MM/DD/slug-d8) quando existe.
  if (item?.url_path) return `${siteBasePath()}${item.url_path}/`;
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
  const isEn = state.lang === "en";
  const routeSeo = {
    home: {
      title: isEn ? "Notícias de Ontem | Memory of the Portuguese press" : "Notícias de Ontem | Memória da imprensa portuguesa",
      description: isEn
        ? "Explore stories preserved by Arquivo.pt, compare different years, and rediscover the Portuguese news memory day by day."
        : "Explore notícias preservadas pelo Arquivo.pt, compare diferentes anos e descubra a memória da imprensa portuguesa em cada dia.",
      path: routeUrl("inicio"),
      type: "website",
    },
    calendar: {
      title: isEn ? "Calendar of historical stories | Notícias de Ontem" : "Calendário de notícias históricas | Notícias de Ontem",
      description: isEn
        ? "Pick a date and discover stories from different years preserved by Arquivo.pt."
        : "Escolha uma data e descubra notícias de diferentes anos preservadas pelo Arquivo.pt.",
      path: routeUrl("calendario"),
      type: "website",
    },
    topics: {
      title: isEn ? "How topics evolved in the Portuguese press | Notícias de Ontem" : "Evolução de temas na imprensa portuguesa | Notícias de Ontem",
      description: isEn
        ? "Track how topics evolved across the preserved Portuguese press and filter by newspaper and period."
        : "Analise a evolução de temas na imprensa portuguesa preservada e filtre os resultados por jornal e período.",
      path: routeUrl("temas"),
      type: "website",
    },
    docs: {
      title: isEn ? "How the project works | Notícias de Ontem" : "Como funciona o projeto | Notícias de Ontem",
      description: isEn
        ? "Learn about the sources, coverage, and method used to select content preserved by Arquivo.pt."
        : "Conheça as fontes, a cobertura e o método usado para selecionar conteúdos preservados pelo Arquivo.pt.",
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
    inLanguage: isEn ? "en-US" : "pt-PT",
    isBasedOn: "https://arquivo.pt/",
  };

  if (route === "news") {
    const item = findNewsItem(selectedNewsIdFromLocation());
    if (item) {
      const title = titleWithYear(item);
      seo = {
        title: `${title} | Notícias de Ontem`,
        description: localized(item, "summary")
          || (isEn ? `Read ${title} and the source preserved on Arquivo.pt.` : `Consulte ${title} e a fonte preservada no Arquivo.pt.`),
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
        inLanguage: isEn ? "en-US" : "pt-PT",
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

function renderHeroDots(heroItems) {
  const dots = document.getElementById("hero-dots");
  if (!dots) return;
  dots.innerHTML = heroItems.map((item, index) => `
    <button type="button" class="hero-dot${index === state.slide ? " active" : ""}" data-hero-dot="${index}" aria-label="${escapeHtml(`${index + 1} — ${titleWithYear(item)}`)}"><span class="hero-dot-fill"></span></button>
  `).join("");
}

function renderHero() {
  const heroItems = state.data?.carousel?.length ? state.data.carousel : [state.data?.featured].filter(Boolean);
  const item = heroItems.length ? heroItems[state.slide % heroItems.length] : null;
  const hero = document.getElementById("hero");
  const instagram = document.getElementById("hero-instagram");
  const source = document.getElementById("hero-source");
  const detail = document.getElementById("hero-detail");
  renderHeroDots(heroItems);
  // O título da secção varia com o destaque: principal, da semana, do dia…
  const eyebrowKeys = ["heroEyebrow", "heroEyebrowWeek", "heroEyebrowDay", "heroEyebrowFeatured"];
  const heroEyebrow = document.querySelector(".hero-content .eyebrow");
  if (heroEyebrow) heroEyebrow.textContent = t(eyebrowKeys[(state.slide || 0) % eyebrowKeys.length]);
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
  // Título limpo (sem "?") + ano de volta na pílula pequena.
  setText("#hero-detail", bannerTitle(item));
  setText("#hero-year", item.original_year ? `${t("yearOnly")} ${item.original_year}` : "");
  const heroBadges = document.getElementById("hero-badges");
  if (heroBadges) heroBadges.innerHTML = `${sourceTypeChip(item)}${relevanceBadge(item)}${networkBadgesHtml(item)}`;
  if (detail && item.page_id) {
    detail.href = newsPageUrl(item);
    detail.dataset.newsId = item.page_id;
  }
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

function cardMetaHtml(item) {
  const parts = [
    ...itemMeta(item).map(escapeHtml),
    sourceTypeChip(item),
    relevanceBadge(item, { compact: true }),
    networkBadgesHtml(item),
  ].filter(Boolean);
  return parts.join("");
}

function renderCarousel() {
  const carousel = document.getElementById("carousel");
  if (!carousel) return;
  const items = state.data?.carousel || [];
  carousel.innerHTML = `<div class="carousel-track">${items.map((item) => {
    return `
      <article class="story-card" style="background-image: url('${escapeHtml(assetPath(item.banner_image || item.image || "assets/icon.png"))}')">
        <div class="story-shade"></div>
        <div class="content">
          <div class="meta">${cardMetaHtml(item)}</div>
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
    return `
      <article class="latest-card">
        ${cardImage(item, true)}
        <div class="content">
          <div class="meta">${cardMetaHtml(item)}</div>
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
    .filter((item) => monthDay(item.date) === targetMonthDay && targetYears.has(dateYear(item.date)));
}

function calendarPostsForMonth(year, month) {
  const monthStr = String(month).padStart(2, "0");
  return (state.data?.all || [])
    .filter((item) => dateYear(item.date) === year && String(item.date || "").slice(5, 7) === monthStr);
}

function weekRangeFor(dateValue) {
  // Semana de domingo a sábado contendo a data.
  const [year, month, day] = String(dateValue).split("-").map(Number);
  const date = new Date(year, month - 1, day);
  const start = new Date(date);
  start.setDate(date.getDate() - date.getDay());
  const days = [];
  for (let index = 0; index < 7; index += 1) {
    const current = new Date(start);
    current.setDate(start.getDate() + index);
    days.push(isoDate(current.getFullYear(), current.getMonth() + 1, current.getDate()));
  }
  return { start: days[0], end: days[6], days };
}

// Ordenação por badge: nível menor = mais importante; empate por data desc.
function relevanceSortKey(item) {
  const level = Number(item?.relevance_level) || 4;
  return level;
}

function sortByRelevanceDesc(items) {
  return [...items].sort((left, right) => {
    const levelDiff = relevanceSortKey(left) - relevanceSortKey(right);
    if (levelDiff) return levelDiff;
    return `${right.date || ""}-${right.slot || 0}`.localeCompare(`${left.date || ""}-${left.slot || 0}`);
  });
}

// Publicações do projeto do período: ordenadas por badge, máx. 6 no topo.
function projectPostsForPeriod(periodDays) {
  const postMap = new Map();
  const register = (item) => {
    if (item?.page_id && !postMap.has(item.page_id)) postMap.set(item.page_id, item);
  };
  if (periodDays.length === 1) {
    for (const item of calendarPostsForDate(periodDays[0])) register(item);
  } else if (periodDays.length === 7) {
    const { start, end } = weekRangeFor(periodDays[0]);
    for (const item of calendarPostsForMonth(dateYear(start), Number(start.slice(5, 7)))) {
      if (item.date >= start && item.date <= end) register(item);
    }
    for (const item of calendarPostsForMonth(dateYear(start) - 1, Number(start.slice(5, 7)))) {
      const anniversary = `${dateYear(start)}${item.date.slice(4)}`;
      if (anniversary >= start && anniversary <= end) register(item);
    }
  } else {
    const monthStr = String(periodDays[0].slice(5, 7));
    for (const item of calendarPostsForMonth(dateYear(periodDays[0]), Number(monthStr))) register(item);
  }
  return sortByRelevanceDesc([...postMap.values()]).slice(0, CALENDAR_POSTS_LIMIT);
}

// Notícias (não posts) do período, ordenadas por badge.
function periodNews(periodDays) {
  const seen = new Set();
  const items = [];
  const selectedYear = dateYear(periodDays[0]);
  for (const day of periodDays) {
    const targetMonthDay = monthDay(day);
    const candidates = [
      ...(state.data?.calendar?.recommendations_by_day?.[targetMonthDay] || []),
      ...state.calendarRecommendations.filter((item) => monthDay(item.date || item.captured_at || "") === targetMonthDay),
    ];
    for (const item of candidates) {
      const key = item.page_id || titleKey(item.title);
      if (!key || seen.has(key)) continue;
      // Vista "Dia exato": só itens cuja data original é exatamente aquela.
      if (state.calendarView === "exact" && periodDays.length === 1) {
        const itemYear = dateYear(item.event_date || item.date || `${item.original_year}-01-01`);
        const itemMonthDay = monthDay(item.event_date || item.date || `${item.original_year}-01-01`);
        if (itemYear !== selectedYear || itemMonthDay !== targetMonthDay) continue;
      }
      seen.add(key);
      items.push(item);
    }
  }
  return sortByRelevanceDesc(items);
}

// Posts no "dia exato": dia de publicação ou o dia+ano da notícia original.
function exactDatePosts(dateValue) {
  const targetMonthDay = monthDay(dateValue);
  const selectedYear = dateYear(dateValue);
  return sortByRelevanceDesc((state.data?.all || []).filter((item) => {
    if (item.date === dateValue) return true;
    return monthDay(item.date) === targetMonthDay
      && String(item.original_year || "") === String(selectedYear)
      && dateYear(item.date) > selectedYear;
  }));
}

function recommendationListHtml(items) {
  if (!items.length) return "";
  return `<ol class="recommendation-list">${items.map((item) => `
      <li>
        <a href="${escapeHtml(newsPageUrl(item))}" data-news-id="${escapeHtml(item.page_id)}">
          <span>${escapeHtml(item.original_year || dateYear(item.date))}</span>
          <strong>${escapeHtml(localized(item, "title"))}</strong>
          <em>${escapeHtml([topicSourceLabel(item.domain || item.source_profile), "Arquivo.pt"].filter(Boolean).join(" · "))}</em>
          ${relevanceBadge(item, { compact: true })}
        </a>
      </li>
    `).join("")}</ol>`;
}

function renderCalendarGrid() {
  const grid = document.getElementById("calendar-grid");
  if (!grid) return;

  const postDates = new Set(state.data?.calendar?.post_dates || []);
  const recommendationDays = state.data?.calendar?.recommendations_by_day || {};

  if (state.calendarFormat === "week") {
    const { days } = weekRangeFor(state.selectedDate);
    const weekdayLabels = state.lang === "pt"
      ? ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
      : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const cells = weekdayLabels.map((label) => `<div class="calendar-weekday">${escapeHtml(label)}</div>`);
    for (const day of days) {
      const hasPosts = postDates.has(day) || postDates.has(isoDate(dateYear(day) - 1, Number(day.slice(5, 7)), Number(day.slice(8, 10))));
      const hasRecommendations = Boolean(recommendationDays[monthDay(day)]?.length);
      cells.push(`
        <button type="button" class="calendar-day ${day === state.selectedDate ? "active" : ""}" data-date="${day}">
          <span>${Number(day.slice(8, 10))}</span>
          <small>${hasPosts || hasRecommendations ? "•" : ""}</small>
        </button>
      `);
    }
    grid.classList.add("calendar-grid-week");
    grid.innerHTML = cells.join("");
    return;
  }

  grid.classList.remove("calendar-grid-week");
  const firstDay = new Date(state.calendarYear, state.calendarMonth - 1, 1);
  const daysInMonth = new Date(state.calendarYear, state.calendarMonth, 0).getDate();
  const offset = (firstDay.getDay() + 6) % 7;
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
  const week = weekRangeFor(state.selectedDate);
  const viewingMonth = dateYear(state.selectedDate) !== state.calendarYear
    || Number(state.selectedDate.slice(5, 7)) !== state.calendarMonth;

  let periodDays;
  let headingDate;
  let headingTitle;
  let posts;
  let recommendations;
  const targetTotal = state.data?.calendar?.target_total_per_day || 25;

  if (state.calendarView === "exact") {
    // "Dia exato": apenas o que aconteceu/preservou nessa data precisa.
    periodDays = [state.selectedDate];
    posts = state.calendarSource ? [] : exactDatePosts(state.selectedDate).slice(0, CALENDAR_POSTS_LIMIT);
    recommendations = periodNews(periodDays);
    headingDate = formatDate(state.selectedDate);
    headingTitle = `${t("exactDayTitle")} ${headingDate}`.trim();
  } else if (state.calendarFormat === "week") {
    periodDays = week.days;
    posts = state.calendarSource ? [] : projectPostsForPeriod(week.days);
    recommendations = periodNews(week.days).slice(0, Math.max(targetTotal - posts.length, 0));
    const startDay = Number(week.start.slice(8, 10));
    const endDay = Number(week.end.slice(8, 10));
    const startLabel = `${startDay} ${monthName(Number(week.start.slice(5, 7)) - 1)}`;
    const endLabel = `${endDay} ${monthName(Number(week.end.slice(5, 7)) - 1)}`;
    headingDate = `${startLabel} ${t("weekRangeJoin")} ${endLabel}`;
    headingTitle = `${t("monthRecommendationsTitle")} ${headingDate}:`;
  } else if (viewingMonth) {
    const monthDays = Array.from(
      { length: new Date(state.calendarYear, state.calendarMonth, 0).getDate() },
      (_, index) => isoDate(state.calendarYear, state.calendarMonth, index + 1),
    );
    periodDays = monthDays;
    posts = state.calendarSource ? [] : projectPostsForPeriod(monthDays);
    recommendations = periodNews(monthDays).slice(0, Math.max(targetTotal - posts.length, 0));
    headingDate = `${monthName(state.calendarMonth - 1)} ${state.calendarYear}`;
    headingTitle = `${t("monthRecommendationsTitle")} ${headingDate}:`;
  } else {
    periodDays = [state.selectedDate];
    posts = state.calendarSource ? [] : projectPostsForPeriod(periodDays);
    recommendations = calendarRecommendationsForDate(state.selectedDate, posts)
      .slice(0, Math.max(targetTotal - posts.length, 0));
    headingDate = formatDate(state.selectedDate);
    headingTitle = t("dayRecommendationsTitle");
  }

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
        <p class="eyebrow">${escapeHtml(headingDate)}</p>
        <h2>${escapeHtml(headingTitle)}</h2>
      </div>
    </div>
    ${stateMessage}
    ${posts.length ? `
      <div class="day-posts-block">
        <h3 class="day-posts-title">${escapeHtml(t("projectPostsTitle"))}</h3>
        <div class="day-post-grid">${posts.map((item) => storyCard(item, { compactImage: true, showDate: true })).join("")}</div>
      </div>` : ""}
    ${recommendationListHtml(recommendations)}
  `;
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
  const source = document.getElementById("calendar-source");
  const largePicker = document.getElementById("calendar-picker-panel");
  if (largePicker) largePicker.hidden = !state.calendarPickerVisible;
  setText("#calendar-month-label", monthName(state.calendarMonth - 1));
  setText("#calendar-year-label", String(state.calendarYear));
  setText("#calendar-date-label", formatDate(state.selectedDate));
  // Estado dos controlos de formato e vista (segmented controls).
  for (const button of document.querySelectorAll("[data-calendar-format]")) {
    const active = button.getAttribute("data-calendar-format") === state.calendarFormat;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }
  for (const button of document.querySelectorAll("[data-calendar-view]")) {
    const active = button.getAttribute("data-calendar-view") === state.calendarView;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }
  if (!source) return;
  const sources = calendarSourcesForDate(state.selectedDate);
  if (state.calendarSource && !sources.includes(state.calendarSource)) state.calendarSource = "";
  source.innerHTML = [
    `<option value="">${escapeHtml(t("calendarAllSources"))}</option>`,
    ...sources.map((domain) => `<option value="${escapeHtml(domain)}"${domain === state.calendarSource ? " selected" : ""}>${escapeHtml(topicSourceLabel(domain))}</option>`),
  ].join("");
}

function storyCard(item, options = {}) {
  const imageHtml = options.compactImage ? cardImage(item, true) : "";
  return `
    <article class="${options.className || "latest-card"}">
      ${imageHtml}
      <div class="content">
        <div class="meta">${cardMetaHtml(item)}</div>
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
  // Aceita URL limpo (/noticia/AAAA/MM/DD/slug-d8), alias (/noticia/noticia-hash)
  // e o legado ?id=.
  const pathMatch = decodeURIComponent(window.location.pathname).match(/\/noticia\/(.+?)\/?$/i);
  if (pathMatch) return pathMatch[1];
  return new URLSearchParams(window.location.search).get("id") || "";
}

function findNewsItem(pageId) {
  if (!pageId) return null;
  const sources = [
    ...(state.data?.all || []),
    ...Object.values(state.dynamicNews || {}),
    ...state.calendarRecommendations,
    ...Object.values(state.data?.calendar?.recommendations_by_day || {}).flat(),
  ];
  return (
    sources.find((item) => item && item.page_id === pageId) ||
    // URL limpo: casar pelo caminho completo (noticia/AAAA/MM/DD/slug-d8).
    sources.find((item) => item && item.url_path === pageId) ||
    sources.find((item) => item && item.url_path && item.url_path.endsWith(`/${pageId}`)) ||
    null
  );
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

function articleParagraphs(item) {
  const seen = new Set();
  const paragraphs = [];
  [localized(item, "summary"), item.body, item.caption].forEach((text) => {
    const value = String(text || "").trim();
    if (!value || seen.has(value)) return;
    seen.add(value);
    paragraphs.push(value);
  });
  return paragraphs;
}

function snapshotCaptureDate(item) {
  const match = String(item?.source_url || "").match(/wayback\/(\d{14})/);
  if (!match) return "";
  const value = match[1];
  const date = new Date(`${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}T12:00:00`);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(state.lang === "pt" ? "pt-PT" : "en-US", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(date);
}

// Pontuação detalhada do badge ("Porquê este nível?") — tabela na página.
function relevanceScoresHtml(item) {
  const level = Number(item?.relevance_level);
  const scores = item?.relevance_scores || {};
  const hasScores = scores && Object.keys(scores).length;
  if (!level || !hasScores) return "";
  const rows = [
    ["scoreImpact", "impacto_historico"],
    ["scoreScope", "dimensao_impacto"],
    ["scoreConsequences", "consequencias"],
    ["scoreLater", "relevancia_posterior"],
    ["scoreDuration", "dimensao_duracao"],
    ["scoreMedia", "relevancia_mediatica"],
    ["scoreUniqueness", "singularidade"],
  ];
  return `
    <section class="news-article-relevance">
      <h2 class="news-article-sub">${escapeHtml(t("relevanceWhy"))}</h2>
      <div class="relevance-scores">
        ${rows.map(([key, field]) => {
          const value = Number(scores[field]);
          if (!Number.isFinite(value)) return "";
          return `
            <div class="relevance-score-row">
              <span class="relevance-score-label">${escapeHtml(t(key))}</span>
              <span class="relevance-score-bar"><span style="width:${Math.max(0, Math.min(100, value))}%"></span></span>
              <span class="relevance-score-value">${Math.round(value)}</span>
            </div>
          `;
        }).join("")}
      </div>
      ${item.relevance_justification ? `<p class="relevance-justification">${escapeHtml(item.relevance_justification)}</p>` : ""}
    </section>
  `;
}

// Módulo "No mesmo dia": outras notícias do projeto nesta data, noutros anos.
function sameDayHtml(item) {
  const targetMonthDay = monthDay(item.date || "");
  if (!targetMonthDay) return "";
  const others = (state.data?.all || [])
    .filter((other) => other.page_id !== item.page_id && monthDay(other.date) === targetMonthDay)
    .sort((left, right) => `${right.date}-${right.slot || 0}`.localeCompare(`${left.date}-${left.slot || 0}`))
    .slice(0, 4);
  if (!others.length) return "";
  return `
    <section class="news-article-same-day">
      <h2 class="news-article-sub">${escapeHtml(t("sameDayTitle"))}</h2>
      <p class="same-day-lead">${escapeHtml(t("sameDayLead"))}</p>
      <div class="same-day-grid">
        ${others.map((other) => `
          <a class="same-day-card" href="${escapeHtml(newsPageUrl(other))}" data-news-id="${escapeHtml(other.page_id)}">
            <span class="same-day-year">${escapeHtml(other.original_year || dateYear(other.date))}</span>
            <strong>${escapeHtml(cleanTitle(other))}</strong>
            ${relevanceBadge(other, { compact: true })}
          </a>
        `).join("")}
      </div>
    </section>
  `;
}

// Navegação anterior/seguinte dentro da lista ordenada por data/nível.
function adjacentNewsHtml(item) {
  const all = [...(state.data?.all || [])].sort((left, right) =>
    `${left.date}-${left.slot || 0}`.localeCompare(`${right.date}-${right.slot || 0}`));
  const index = all.findIndex((other) => other.page_id === item.page_id);
  if (index < 0) return "";
  const neighbours = [
    index > 0 ? all[index - 1] : null,
    index < all.length - 1 ? all[index + 1] : null,
  ];
  if (!neighbours[0] && !neighbours[1]) return "";
  return `
    <nav class="news-article-neighbours" aria-label="${escapeHtml(t("sameDayTitle"))}">
      ${neighbours[0] ? `<a class="neighbour prev" href="${escapeHtml(newsPageUrl(neighbours[0]))}" data-news-id="${escapeHtml(neighbours[0].page_id)}"><span>‹ ${escapeHtml(t("previousStory"))}</span><strong>${escapeHtml(cleanTitle(neighbours[0]))}</strong></a>` : "<span></span>"}
      ${neighbours[1] ? `<a class="neighbour next" href="${escapeHtml(newsPageUrl(neighbours[1]))}" data-news-id="${escapeHtml(neighbours[1].page_id)}"><span>${escapeHtml(t("nextStory"))} ›</span><strong>${escapeHtml(cleanTitle(neighbours[1]))}</strong></a>` : "<span></span>"}
    </nav>
  `;
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
        <a class="button primary" href="${escapeHtml(routeUrl("calendario"))}" data-route-link="calendar">${escapeHtml(t("newsBack"))}</a>
      </div>
    `;
    updateDocumentMetadata();
    return;
  }

  const title = titleWithYear(item);
  const image = assetPath(item.detail_image || item.image || item.banner_image || "assets/icon.png");
  const category = item.category || "";
  const dateLine = [
    item.date ? `${t("publishedOn")} ${formatDate(item.date)}` : "",
    item.original_year ? `${t("originalYearLabel")} ${item.original_year}` : "",
  ].filter(Boolean).join(" · ");
  const paragraphs = articleParagraphs(item);
  const snapshotUrl = item.snapshot_url ? assetPath(item.snapshot_url) : "";
  const capturedOn = snapshotCaptureDate(item);
  const [lead, ...restParagraphs] = paragraphs;
  // Capa e snapshot duplicadas: no desktop ficam FIXAS na coluna direita
  // (vista global, sem deslizar); em ecrãs menores a capa surge depois do
  // título e a snapshot no fim do texto, antes de "No mesmo dia".
  const coverHtml = image ? `
    <figure class="news-cover">
      <img id="news-detail-image" src="${escapeHtml(image)}" alt="${escapeHtml(title)}">
    </figure>` : "";
  const snapshotHtml = snapshotUrl ? `
    <section class="news-snapshot">
      <h2 class="news-article-sub">${escapeHtml(t("snapshotSectionTitle"))}</h2>
      <figure class="news-article-snapshot-frame">
        <div class="news-article-snapshot-head">
          <strong>arquivo.pt</strong>
          ${capturedOn ? `<span>${escapeHtml(`${t("snapshotCaptured")} ${capturedOn}`)}</span>` : ""}
        </div>
        <img src="${escapeHtml(snapshotUrl)}" alt="${escapeHtml(t("snapshotCaption"))}" loading="lazy">
        <figcaption>
          <span>${escapeHtml(t("snapshotCaption"))}</span>
          ${item.source_url ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(t("viewOriginal"))} →</a>` : ""}
        </figcaption>
      </figure>
    </section>` : "";
  container.innerHTML = `
    <nav class="news-breadcrumb" aria-label="Breadcrumb">
      <a href="${escapeHtml(routeUrl("inicio"))}" data-route-link="home">${escapeHtml(t("breadcrumbHome"))}</a>
      <span aria-hidden="true">›</span>
      <a href="${escapeHtml(routeUrl("calendario"))}" data-route-link="calendar">${escapeHtml(t("breadcrumbCalendar"))}</a>
      <span aria-hidden="true">›</span>
      <span class="current">${escapeHtml(title)}</span>
    </nav>
    <article class="news-article">
      <div class="news-layout">
        <header class="news-head">
          <p class="news-article-meta">
            ${category ? `<span class="meta-pill">${escapeHtml(category)}</span>` : ""}
            ${sourceTypeChip(item)}
            ${relevanceBadge(item)}
          </p>
          <h1 id="news-detail-title">${escapeHtml(title)}</h1>
          ${dateLine ? `<p class="news-article-dates">${escapeHtml(dateLine)}</p>` : ""}
        </header>
        ${coverHtml}
        <div class="news-text">
          ${lead ? `<p class="news-article-lead">${escapeHtml(lead)}</p>` : ""}
          ${restParagraphs.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join("")}
          <div class="news-article-actions">
            ${item.instagram_url ? `<a class="button primary" href="${escapeHtml(item.instagram_url)}" target="_blank" rel="noreferrer">${escapeHtml(t("newsOpenInstagram"))}</a>` : ""}
            ${item.source_url ? `<a class="button secondary" href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(t("newsOpenArquivo"))}</a>` : ""}
          </div>
        </div>
        ${snapshotHtml}
      </div>
      ${sameDayHtml(item)}
      ${adjacentNewsHtml(item)}
    </article>
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
  return `ndo-topic-v4-verified:${normalizedTopicText(query)}:${source}:${fromDate}:${toDate}`;
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
    maxItems: String(options.maxItems ?? 1),
    offset: String(options.offset ?? 0),
    dedupValue: "0",
  });
  // Datas vazias são omitidas: sondas de presença vão sem filtro temporal
  // (o filtro from do Arquivo.pt falha para conteúdo de meados de 2021 em diante).
  if (fromValue) params.set("from", topicApiBoundary(fromValue, false));
  if (toValue) params.set("to", topicApiBoundary(toValue, true));
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
    const timeout = window.setTimeout(() => controller.abort(), 35000);
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
      // 429/503: limite por minuto ou indisponibilidade — esperar mais antes
      // de repetir evita converter falhas temporárias em "não verificado".
      const message = String(error?.message || "");
      if (message.includes("429") || message.includes("503")) {
        if (attempt < 2) await new Promise((resolve) => window.setTimeout(resolve, 2200 * (attempt + 1)));
      } else if (attempt < 2) {
        await new Promise((resolve) => window.setTimeout(resolve, 400 * (attempt + 1)));
      }
    } finally {
      window.clearTimeout(timeout);
      parentSignal?.removeEventListener("abort", abortRequest);
    }
  }
  throw lastError || new Error("Arquivo.pt unavailable");
}

function updateTopicProgress(done, total, currentYear = "") {
  const progress = document.getElementById("topic-progress");
  const bar = document.getElementById("topic-progress-bar");
  const text = document.getElementById("topic-progress-text");
  if (!progress || !bar || !text) return;
  const percent = total ? Math.round((done / total) * 100) : 100;
  progress.hidden = false;
  bar.max = 100;
  bar.value = percent;
  const yearLabel = currentYear ? (state.lang === "pt" ? ` · a verificar ${currentYear}` : ` · verifying ${currentYear}`) : "";
  text.textContent = state.lang === "pt" ? `A carregar ${percent}%${yearLabel}` : `Loading ${percent}%${yearLabel}`;
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
const TOPIC_MAX_PROBES_PER_SEARCH = 500;
const TOPIC_MIN_REQUEST_INTERVAL_MS = 200;
// O filtro `from` do Arquivo.pt devolve 0 resultados para conteúdo a partir
// de meados de 2021 (confirmado a 2026-09): a partir daqui, um 0 só é aceito
// se uma sonda SEM datas também não tiver resultados.
const TOPIC_DATE_FILTER_BREAK = "2021-07-01";
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

// Dias entre duas datas (para os limites de granularidade).
function topicDaysBetween(fromDate, toDate) {
  const from = new Date(`${fromDate}T00:00:00Z`);
  const to = new Date(`${toDate}T00:00:00Z`);
  return Math.round((to - from) / 86400000);
}

// Último dia de um mês (trata anos bissextos: 29 de fevereiro).
function topicLastDayOfMonth(year, month) {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

// Fatias por granularidade: ano (default), mês ou dia. Cada fatia tem um
// `label` estável (YYYY | YYYY-MM | YYYY-MM-DD) e as datas exatas de borda.
function topicPeriodSlices(fromDate, toDate, granularity = "year") {
  if (granularity === "month" || granularity === "day") {
    const slices = [];
    let [year, month, day] = fromDate.split("-").map(Number);
    const [endYear, endMonth, endDay] = toDate.split("-").map(Number);
    let guard = 0;
    while (guard < 800) {
      guard += 1;
      const lastDay = topicLastDayOfMonth(year, month);
      const sliceEndDay = Math.min(lastDay, granularity === "day" ? lastDay : lastDay);
      const sliceFrom = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      const sliceToDate = granularity === "day" ? sliceFrom : `${year}-${String(month).padStart(2, "0")}-${String(sliceEndDay).padStart(2, "0")}`;
      const clippedTo = sliceToDate > toDate ? toDate : sliceToDate;
      const label = granularity === "day" ? sliceFrom : `${year}-${String(month).padStart(2, "0")}`;
      slices.push({
        label,
        year,
        month,
        fromDate: sliceFrom,
        toDate: clippedTo,
      });
      if (granularity === "day") {
        day += 1;
        if (day > lastDay) {
          day = 1;
          month += 1;
          if (month > 12) {
            month = 1;
            year += 1;
          }
        }
      } else {
        month += 1;
        day = 1;
        if (month > 12) {
          month = 1;
          year += 1;
        }
      }
      if (`${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}` > toDate) break;
      if (year > endYear || (year === endYear && month > endMonth)) break;
    }
    return slices;
  }
  return topicYearSlices(fromDate, toDate);
}

// Limites de desbloqueio: mês exige ≤ 2 anos; dia exige ≈ 1 mês corrido.
function topicGranularityUnlocked(fromDate, toDate, granularity) {
  if (granularity === "month") {
    const [fy, fm] = fromDate.split("-").map(Number);
    const [ty, tm] = toDate.split("-").map(Number);
    return ((ty - fy) * 12 + (tm - fm)) <= 25;
  }
  if (granularity === "day") {
    const span = topicDaysBetween(fromDate, toDate);
    return span >= 1 && span <= 32;
  }
  return true;
}

async function fetchTopicSeries(query, source, fromDate, toDate, signal, onProgress = null, onSeriesUpdate = null, granularity = "year") {
  const slices = topicPeriodSlices(fromDate, toDate, granularity);
  const results = new Array(slices.length);
  let cursor = 0;
  let completed = 0;
  let failed = 0;

  const worker = async () => {
    while (cursor < slices.length) {
      const index = cursor;
      cursor += 1;
      const slice = slices[index];
      if (onProgress) onProgress(completed, slices.length, slice.label, "start");
      try {
        const fromTimestamp = topicApiBoundary(slice.fromDate, false);
        const toTimestamp = topicApiBoundary(slice.toDate, true);
        let count = await countTopicIntervalExactly(query, source, fromTimestamp, toTimestamp, signal);
        // Detecção de falso zero: se o filtro de datas do arquivo falhar para
        // este período mas o tema tem capturas sem filtro temporal, o período
        // fica NÃO verificado em vez de zero.
        if (count === 0 && slice.toDate >= TOPIC_DATE_FILTER_BREAK) {
          let presence;
          try {
            presence = await fetchTopicProbe(query, source, "", "", 0, signal);
          } catch (presenceError) {
            // Sem conseguir provar presença, o zero continua inconclusivo:
            // marca como falha do filtro de datas em vez de zero.
            presenceError.code = presenceError.code || "date_filter_unavailable";
            throw presenceError;
          }
          if (presence.hasResult) {
            throw Object.assign(new Error("Arquivo.pt date filter unavailable"), { code: "date_filter_unavailable" });
          }
        }
        results[index] = {
          year: slice.year,
          label: slice.label,
          from_date: slice.fromDate,
          to_date: slice.toDate,
          count,
          failed: false,
        };
      } catch (error) {
        if (signal.aborted) throw error;
        results[index] = {
          year: slice.year,
          label: slice.label,
          from_date: slice.fromDate,
          to_date: slice.toDate,
          count: null,
          failed: true,
          error_code: error?.code || "request_failed",
        };
        failed += 1;
      }
      completed += 1;
      if (onProgress) onProgress(completed, slices.length, slice.label, "done");
      if (onSeriesUpdate) onSeriesUpdate(slice.label, results[index]);
    }
  };

  await Promise.all(Array.from({ length: Math.min(10, slices.length) }, () => worker()));
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
  return new Intl.DateTimeFormat(state.lang === "pt" ? "pt-PT" : "en-US", {
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
  renderTopicGranularity();
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
  const granularityParam = params.get("granularidade");
  if (["year", "month", "day"].includes(granularityParam)) state.topicGranularity = granularityParam;
  renderTopicAnalysisRows();
  fromInput.value = state.topicFromDate;
  toInput.value = state.topicToDate;
  showValues.checked = state.topicShowValues;
  applyTopicDateLimits();
}

// Controlo de granularidade: Por ano sempre ativo; Mês exige ≤2 anos e
// Dia ≈1 mês. Bloqueados mostram a razão ao passar o rato ou clicar.
function renderTopicGranularity() {
  const container = document.getElementById("topic-granularity");
  if (!container) return;
  const fromInput = document.getElementById("topic-from-date");
  const toInput = document.getElementById("topic-to-date");
  const hint = document.getElementById("topic-granularity-hint");
  const fromDate = fromInput?.value || state.topicFromDate;
  const toDate = toInput?.value || state.topicToDate;
  let unlockedText = "";
  for (const button of container.querySelectorAll("[data-topic-granularity]")) {
    const granularity = button.dataset.topicGranularity;
    const unlocked = topicGranularityUnlocked(fromDate, toDate, granularity);
    button.classList.toggle("locked", !unlocked);
    button.classList.toggle("active", state.topicGranularity === granularity);
    button.setAttribute("aria-pressed", String(state.topicGranularity === granularity));
    button.dataset.locked = unlocked ? "0" : "1";
    if (!unlocked) {
      unlockedText = t(granularity === "month" ? "topicGranularityMonthTip" : "topicGranularityDayTip");
      button.setAttribute("data-tip", unlockedText);
    } else {
      button.removeAttribute("data-tip");
    }
  }
  if (hint) {
    hint.hidden = !unlockedText || state.topicGranularity === "year";
    hint.textContent = state.topicGranularity === "year" ? "" : (state.topicGranularity === "month" || state.topicGranularity === "day") && !topicGranularityUnlocked(fromDate, toDate, state.topicGranularity) ? unlockedText : "";
  }
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
  const granularity = state.topicGranularity === "month" || state.topicGranularity === "day" ? state.topicGranularity : "year";
  // Sem dados (ou valores residuais), a escala mostra o padrão 0–10 mil:
  // nunca os eixos degenerados "1,1,1,0,0".
  const hasVerifiedData = verifiedSeries.length > 0;
  const positiveCounts = verifiedSeries.map((item) => item.count).filter((count) => count > 0);
  const dataMax = hasVerifiedData ? Math.max(...verifiedSeries.map((item) => item.count), 1) : 0;
  const defaultScale = !hasVerifiedData || dataMax < 10;
  const maxCount = defaultScale ? 10000 : dataMax;
  const minPositive = positiveCounts.length ? Math.min(...positiveCounts) : 0;
  const useLogScale = !defaultScale && minPositive > 0 && maxCount / minPositive >= 100;
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

  // Eixo X por granularidade + divisores leves de mês nas vistas de dia.
  let yearLabels = "";
  let monthDividers = "";
  if (granularity === "year") {
    yearLabels = baseSeries.map((item, index) => {
      if (index % labelStep !== 0 && index !== baseSeries.length - 1) return "";
      return `<text x="${xForIndex(index)}" y="${height - 20}" class="chart-year" text-anchor="middle">${item.year}</text>`;
    }).join("");
  } else {
    const locale = state.lang === "pt" ? "pt-PT" : "en-US";
    const monthName = (label) => new Intl.DateTimeFormat(locale, { month: "short", timeZone: "UTC" })
      .format(new Date(`${label}-15T00:00:00Z`));
    if (granularity === "month") {
      yearLabels = baseSeries.map((item, index) => {
        if (index % labelStep !== 0 && index !== baseSeries.length - 1) return "";
        return `<text x="${xForIndex(index)}" y="${height - 20}" class="chart-year" text-anchor="middle">${monthName(item.label)} ${item.label.slice(0, 4)}</text>`;
      }).join("");
    } else {
      // Dia: número do dia; linha fina + nome do mês quando o mês muda.
      let previousMonth = "";
      const dividers = [];
      yearLabels = baseSeries.map((item, index) => {
        const month = item.label.slice(0, 7);
        if (previousMonth && month !== previousMonth) {
          const boundary = (xForIndex(index) + xForIndex(index - 1)) / 2;
          dividers.push(`<line x1="${boundary}" y1="${top}" x2="${boundary}" y2="${top + plotHeight}" class="chart-month-divider"></line>`);
          dividers.push(`<text x="${boundary - 4}" y="${height - 20}" class="chart-year chart-month-name" text-anchor="middle">${monthName(previousMonth)}</text>`);
        }
        previousMonth = month;
        if (index % labelStep !== 0 && index !== baseSeries.length - 1) return "";
        return `<text x="${xForIndex(index)}" y="${height - 6}" class="chart-year" text-anchor="middle">${Number(item.label.slice(8, 10))}</text>`;
      }).join("");
      monthDividers = dividers.join("");
    }
  }

  // Períodos falhos: marcador oco na base — visivelmente NÃO zero.
  const failedMarkers = resultSets.map((result, resultIndex) => {
    const color = validTopicColor(result.color, TOPIC_DEFAULT_COLORS[resultIndex]);
    return result.series.map((item, index) => {
      if (item.count !== null || !item.failed) return "";
      const x = xForIndex(index);
      return `<circle class="chart-failed-point" cx="${x}" cy="${top + plotHeight - 4}" r="4" style="stroke:${color}"><title>${escapeHtml(`${result.query} · ${item.label}: ${t("topicFailedPoint")}`)}</title></circle>`;
    }).join("");
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
        ? `<text class="chart-value-label" x="${labelX}" y="${labelY}" text-anchor="middle" style="fill:${color};--i:${index}">${escapeHtml(formatMetricNumber(item.count))}</text>`
        : "";
      return `
        <circle class="chart-point" cx="${x}" cy="${y}" r="4" style="stroke:${color};--i:${index}">
          <title>${escapeHtml(result.query)} · ${item.label}: ${formatMetricNumber(item.count)} ${t("topicMentions")}</title>
        </circle>
        ${valueLabel}
      `;
    }).join("");

    const posts = matchingInstagramPosts(result.query, result.source, state.topicFromDate, state.topicToDate);
    postCount += posts.length;
    const postPoints = posts.map((post, postIndex) => {
      const monthDayOfPost = monthDay(post.date);
      const index = result.series.findIndex((item) => {
        if (granularity === "month") return item.label === `${post.original_year}-${monthDayOfPost.slice(0, 2)}`;
        if (granularity === "day") return item.label === `${post.original_year}-${monthDayOfPost}`;
        return item.year === Number(post.original_year);
      });
      if (index < 0 || !Number.isFinite(result.series[index].count)) return "";
      const y = Math.max(top + 8, yForCount(result.series[index].count) - 15 - ((postIndex % 3) * 11));
      return `<a href="${escapeHtml(newsPageUrl(post))}" data-news-id="${escapeHtml(post.page_id)}"><circle class="chart-post-point" cx="${xForIndex(index)}" cy="${y}" r="5" style="fill:${color}"><title>${escapeHtml(titleWithYear(post))}</title></circle></a>`;
    }).join("");
    return `<path class="chart-line" d="${linePath}" pathLength="1" style="stroke:${color};animation-delay:${resultIndex * 180}ms"></path>${points}${postPoints}`;
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

  container.classList.toggle("loading", Boolean(state.topicLoading));
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
        ${monthDividers}
        ${chartSeries}
        ${failedMarkers}
        ${yearLabels}
      </svg>
    </div>
    ${state.topicLoading ? "" : `
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
    </div>`}
  `;
  const status = document.getElementById("topic-status");
  if (status) {
    const allPeriods = resultSets.flatMap((result) => result.series);
    const failures = allPeriods.filter((item) => item.failed).length;
    const limited = allPeriods.filter((item) => item.error_code === "verification_limit").length;
    // Falhas em períodos recentes = janela em que o filtro de datas do
    // Arquivo.pt falha (independente do código de erro: throttle ou datas).
    const dateFilter = allPeriods.filter((item) => item.failed && String(item.to_date || "") >= TOPIC_DATE_FILTER_BREAK).length;
    if (failures) {
      if (dateFilter) {
        status.textContent = state.lang === "pt"
          ? `${dateFilter} períodos não puderam ser verificados: o filtro de datas do Arquivo.pt está a devolver resultados vazios para conteúdo recente (falha do lado do arquivo, a partir de meados de 2021). Ficam marcados como não verificados — nunca como zero.`
          : `${dateFilter} periods could not be verified: the Arquivo.pt date filter is returning empty results for recent content (an archive-side issue, from mid-2021 on). They are marked as not verified — never as zero.`;
      } else if (limited) {
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
  renderTopicGranularity();
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
  const suffix = state.topicGranularity === "month" ? "-mensal" : state.topicGranularity === "day" ? "-diario" : "";
  return `noticias-de-ontem-${comparison}-${state.topicFromDate}-${state.topicToDate}${suffix}.${extension}`;
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
      ? ["analise", "tema", "fonte", "cor", "total_serie", "mostrar_valores", "intervalo_inicio", "intervalo_fim", "periodo", "resultados_verificados", "estado", "motivo", "metodo", "url_consulta_arquivo_pt", "consultado_em"]
      : ["analysis", "topic", "source", "colour", "series_total", "show_values", "range_start", "range_end", "period", "verified_results", "status", "reason", "method", "arquivo_pt_query_url", "collected_at"],
    ...(state.topicResultSets || []).flatMap((result, resultIndex) => result.series.map((item) => [
      resultIndex + 1,
      result.query,
      result.source || (portuguese ? "todas" : "all"),
      result.color,
      result.total,
      state.topicShowValues ? (portuguese ? "sim" : "yes") : (portuguese ? "nao" : "no"),
      item.from_date,
      item.to_date,
      item.label || item.year,
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
    .chart-axis-value,.chart-year{fill:#5a6a71;font-family:Montserrat,Arial,sans-serif;font-size:12px}
    .chart-line{fill:none;stroke:#0d9ba8;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}
    .chart-point{fill:#fff;stroke:#0d9ba8;stroke-width:3}
    .chart-post-point{fill:#c85d4b;stroke:#fff;stroke-width:2}
    .chart-value-label{stroke:#fff;stroke-width:4;paint-order:stroke;font-family:Montserrat,Arial,sans-serif;font-size:11px;font-weight:700}
    .export-legend-label{fill:#15181d;font-family:Montserrat,Arial,sans-serif;font-size:13px;font-weight:700}
    .export-title{fill:#15181d;font-family:Montserrat,Arial,sans-serif;font-size:18px;font-weight:800}
  `;
  clone.insertBefore(style, clone.firstChild);
  const background = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  background.setAttribute("width", "100%");
  background.setAttribute("height", "100%");
  background.setAttribute("fill", "#ffffff");
  clone.insertBefore(background, style.nextSibling);

  const periodWording = state.lang === "pt"
    ? (state.topicGranularity === "month" ? " com verificação mensal" : state.topicGranularity === "day" ? " com verificação diária" : " com verificação anual")
    : (state.topicGranularity === "month" ? " with monthly verification" : state.topicGranularity === "day" ? " with daily verification" : " with yearly verification");
  const exportTitle = state.lang === "pt"
    ? (resultSets.length === 1
        ? `Evolução de "${resultSets[0].query}" no índice preservado do Arquivo.pt entre ${formatTopicDate(state.topicFromDate)} e ${formatTopicDate(state.topicToDate)}${periodWording}`
        : `Comparação de temas no índice preservado do Arquivo.pt entre ${formatTopicDate(state.topicFromDate)} e ${formatTopicDate(state.topicToDate)}${periodWording}`)
    : (resultSets.length === 1
        ? `Evolution of "${resultSets[0].query}" in the Arquivo.pt preserved index between ${formatTopicDate(state.topicFromDate)} and ${formatTopicDate(state.topicToDate)}${periodWording}`
        : `Topic comparison in the Arquivo.pt preserved index between ${formatTopicDate(state.topicFromDate)} and ${formatTopicDate(state.topicToDate)}${periodWording}`);
  const title = document.createElementNS("http://www.w3.org/2000/svg", "text");
  title.setAttribute("x", String(width / 2));
  title.setAttribute("y", "34");
  title.setAttribute("text-anchor", "middle");
  title.setAttribute("class", "export-title");
  title.textContent = exportTitle;
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
    label.textContent = `${result.query} | ${topicSourceLabel(result.source)} | ${formatMetricNumber(result.total)} ${t("topicMentions")}`;
    legend.appendChild(label);
  });
  clone.appendChild(legend);

  const credit = document.createElementNS("http://www.w3.org/2000/svg", "text");
  credit.setAttribute("x", "62");
  credit.setAttribute("y", String(444 + (resultSets.length * 24)));
  credit.setAttribute("fill", "#5c6b78");
  credit.setAttribute("font-family", "Montserrat, Arial, sans-serif");
  credit.setAttribute("font-size", "12");
  credit.textContent = state.lang === "pt"
    ? "Fonte: Arquivo.pt"
    : "Source: Arquivo.pt";
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

function topicResultsMatchLocation() {
  try {
    const saved = JSON.parse(sessionStorage.getItem("ndo-topic-results") || "null");
    return Boolean(saved && saved.search === window.location.search && Array.isArray(saved.sets) && saved.sets.length);
  } catch {
    return false;
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
  // Resultados da mesma configuração nesta sessão: evita refazer pesquisas
  // longas ao recarregar a página.
  try {
    const saved = JSON.parse(sessionStorage.getItem("ndo-topic-results") || "null");
    if (topicResultsMatchLocation() && saved) {
      state.topicResultSets = saved.sets;
      state.topicSeries = saved.sets[0]?.series || [];
      state.topicTotal = saved.sets.reduce((sum, result) => sum + (Number(result.total) || 0), 0);
    }
  } catch {
    // sessionStorage indisponível; a pesquisa corre normalmente.
  }
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
      ...(state.topicGranularity !== "year" ? { granularidade: state.topicGranularity } : {}),
    }));
  }

  const granularity = topicGranularityUnlocked(fromDate, toDate, state.topicGranularity) ? state.topicGranularity : "year";
  const periodsPerAnalysis = topicPeriodSlices(fromDate, toDate, granularity).length;
  const totalPeriods = periodsPerAnalysis * analyses.length;
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
        // Esqueleto com todos os períodos a null: o gráfico nasce vazio e
        // cresce à medida que cada contagem é verificada.
        results = analyses.map((analysis) => ({
          ...analysis,
          series: topicPeriodSlices(fromDate, toDate, granularity).map((slice) => ({
            year: slice.year,
            label: slice.label,
            from_date: slice.fromDate,
            to_date: slice.toDate,
            count: null,
            failed: false,
          })),
          total: 0,
        }));
        state.topicResultSets = results;
        renderTopicGraph();
        let cursor = 0;
        const worker = async () => {
        while (cursor < analyses.length) {
          const index = cursor;
          cursor += 1;
          const analysis = analyses[index];
          const cacheKey = topicCacheKey(analysis.query, analysis.source, fromDate, toDate) + `:${granularity}`;
          const cached = readTopicCache(cacheKey);
          let result = cached;
          if (cached) {
            completedPeriods += cached.series.length;
            updateTopicProgress(completedPeriods, totalPeriods);
          } else {
            try {
              const seriesIndex = index;
              result = await fetchTopicSeries(
                analysis.query,
                analysis.source,
                fromDate,
                toDate,
                searchAbort.signal,
                (done, total, label, phase) => {
                  if (phase === "start") {
                    // Mostra o período em curso sem avançar o contador.
                    updateTopicProgress(completedPeriods, totalPeriods, label);
                    return;
                  }
                  completedPeriods += 1;
                  updateTopicProgress(completedPeriods, totalPeriods, label);
                },
                (label, entry) => {
                  // Cada período verificado entra no gráfico imediatamente.
                  const resultSet = state.topicResultSets[seriesIndex];
                  const point = resultSet?.series?.find((item) => item.label === label);
                  if (point) {
                    point.count = entry.count;
                    point.failed = entry.failed;
                    point.error_code = entry.error_code;
                    if (Number.isFinite(entry.count)) resultSet.total += entry.count;
                    renderTopicGraph();
                  }
                },
                granularity,
              );
            } catch (error) {
              if (searchAbort.signal.aborted) throw error;
              result = {
                series: topicPeriodSlices(fromDate, toDate, granularity).map((slice) => ({
                  year: slice.year,
                  label: slice.label,
                  from_date: slice.fromDate,
                  to_date: slice.toDate,
                  count: null,
                  failed: true,
                  error_code: error?.code || "request_failed",
                })),
                total: 0,
                complete: false,
              };
              completedPeriods += periodsPerAnalysis;
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
    try {
      sessionStorage.setItem("ndo-topic-results", JSON.stringify({
        search: window.location.search,
        sets: state.topicResultSets,
      }));
    } catch {
      // Sem sessionStorage; os resultados vivem apenas nesta vista.
    }
  } catch (error) {
    if (!searchAbort.signal.aborted && status) status.textContent = t("topicError");
  } finally {
    if (state.topicAbort !== searchAbort) return;
    state.topicLoading = false;
    if (submit) submit.disabled = false;
    if (progress) progress.hidden = true;
    // Render final sem a marca de carregamento: liberta a exportação.
    renderTopicGraph();
  }
}

function formatMetricNumber(value) {
  return new Intl.NumberFormat(state.lang === "pt" ? "pt-PT" : "en-US").format(Math.max(0, Number(value) || 0));
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
      reel.dataset.targetDigit = String(targetDigit);
      reel.dataset.maxDelay = String((index * 55) + (digitsToRight * 16));

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

  // Duplo rAF: garante que o estado inicial dos dígitos é pintado antes de
  // arrancar a transição — sem isto, a animação falha ao chegar por navegação.
  state.counterFrame = window.requestAnimationFrame(() => {
    if (run !== state.counterRun || state.route !== "docs") return;
    state.counterFrame = window.requestAnimationFrame(() => {
      if (run !== state.counterRun || state.route !== "docs") return;
      counters.forEach((element) => element.classList.add("odometer-running"));
      state.counterFrame = null;
      settleOdometers(counters);
    });
  });
}

// No fim da transição, cada rolo é substituído pelo dígito final estático:
// elimina subpixels dos últimos frames (números sempre alinhados) e liberta
// os spans do rolo. Fallback por timeout caso transitionend não dispare.
function settleOdometers(counters) {
  const settleReel = (reel) => {
    if (!reel.isConnected) return;
    // Mantém o wrapper .odometer-digit e troca apenas o conteúdo:
    // as métricas da caixa são idênticas antes e depois — o texto de baixo
    // nunca salta.
    const track = reel.querySelector(".odometer-track");
    if (track) {
      track.style.transition = "none";
      track.style.setProperty("--odometer-shift", "0em");
      track.innerHTML = "";
      const digit = document.createElement("span");
      digit.textContent = reel.dataset.targetDigit || "0";
      track.appendChild(digit);
    }
  };
  counters.forEach((element) => {
    element.querySelectorAll(".odometer-digit").forEach((reel) => {
      const track = reel.querySelector(".odometer-track");
      let settled = false;
      const settleOnce = () => {
        if (settled) return;
        settled = true;
        settleReel(reel);
      };
      track?.addEventListener("transitionend", settleOnce, { once: true });
      const delay = Number(reel.dataset.maxDelay) || 0;
      window.setTimeout(settleOnce, 1250 + delay + 150);
    });
  });
}

// Home em colunas (estilo jornal): à esquerda (~66%) as "Mais notícias";
// à direita a lista dos Marcos Históricos (nível 1, mesmo fora do carrossel)
// e, por baixo, um feed "ao minuto" com as últimas publicações do perfil.
function renderHomeSections() {
  const all = state.data?.all || [];
  const byLevel = (level) => all
    .filter((item) => (Number(item.relevance_level) || 4) === level)
    .sort((left, right) => `${right.date || ""}-${right.slot || 0}`.localeCompare(`${left.date || ""}-${left.slot || 0}`));

  // Coluna principal: Mais notícias (níveis 2-5; os marcos ficam na barra).
  const moreContainer = document.getElementById("home-more");
  const moreColumn = document.getElementById("home-more-column");
  if (moreContainer && moreColumn) {
    const items = byLevel(2).concat(byLevel(3), byLevel(4), byLevel(5)).slice(0, 6);
    moreColumn.hidden = items.length === 0;
    moreContainer.innerHTML = items.map((item) => `
      <article class="latest-card">
        ${cardImage(item, true)}
        <div class="content">
          <div class="meta">${cardMetaHtml(item)}</div>
          <h3><a href="${escapeHtml(newsPageUrl(item))}" data-news-id="${escapeHtml(item.page_id)}">${escapeHtml(cleanTitle(item))}</a></h3>
          <p>${escapeHtml(localized(item, "summary"))}</p>
          <div class="card-actions">
            ${item.source_url ? `<a class="text-link" href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(t("openArquivo"))}</a>` : ""}
          </div>
        </div>
      </article>
    `).join("");
  }

  // Barra lateral: lista dos Marcos Históricos (até 6), com badge.
  const landings = byLevel(1).slice(0, 6);
  const landmarksBlock = document.getElementById("home-level-1-block");
  const landmarksList = document.getElementById("home-level-1");
  if (landmarksBlock && landmarksList) {
    landmarksBlock.hidden = landings.length === 0;
    landmarksList.innerHTML = landings.map((item) => `
      <li>
        <a href="${escapeHtml(newsPageUrl(item))}" data-news-id="${escapeHtml(item.page_id)}">
          <span class="feed-year">${escapeHtml(item.original_year || dateYear(item.date))}</span>
          <strong>${escapeHtml(cleanTitle(item))}</strong>
          ${relevanceBadge(item, { compact: true })}
        </a>
      </li>
    `).join("");
  }

  // Feed "ao minuto": últimas publicações (published primeiro), com tempo relativo.
  const feedBlock = document.getElementById("home-feed-block");
  const feed = document.getElementById("minute-feed");
  if (feedBlock && feed) {
    const published = all.filter((item) => item.instagram_url || (item.network_posts && Object.keys(item.network_posts).length));
    const items = (published.length ? published : all).slice(0, 5);
    feedBlock.hidden = items.length === 0;
    feed.innerHTML = items.map((item) => `
      <li>
        <span class="feed-time">${escapeHtml(relativeTime(item.date))}</span>
        <a href="${escapeHtml(newsPageUrl(item))}" data-news-id="${escapeHtml(item.page_id)}">
          <strong>${escapeHtml(cleanTitle(item))}</strong>
        </a>
        <em>${escapeHtml(localized(item, "summary").slice(0, 110))}${localized(item, "summary").length > 110 ? "…" : ""}</em>
      </li>
    `).join("");
  }
}

// Tempo relativo para o feed ("hoje", "ontem", "há X dias").
function relativeTime(dateValue) {
  if (!dateValue) return "";
  const then = new Date(`${dateValue}T12:00:00`);
  const today = new Date();
  today.setHours(12, 0, 0, 0);
  const days = Math.round((today - then) / 86400000);
  if (days <= 0) return state.lang === "en" ? "Today" : "Hoje";
  if (days === 1) return state.lang === "en" ? "Yesterday" : "Ontem";
  return state.lang === "en" ? `${days} days ago` : `Há ${days} dias`;
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
  renderRelevanceDocs();
  const githubLink = document.getElementById("docs-github");
  if (githubLink) githubLink.href = state.data?.github_url || "https://github.com/Noticias-de-ontem/site";
}

// Secção detalhada "Níveis de relevância histórica" na Documentação:
// níveis, critérios com pesos, exemplo pontuado e regras de curadoria.
function renderRelevanceDocs() {
  const container = document.getElementById("relevance-doc");
  if (!container) return;
  const lang = state.lang === "en" ? "en" : "pt";
  const levels = RELEVANCE_LEVELS[lang];
  const criteria = lang === "en"
    ? [
        ["Historical impact", "30%", "How much the event influenced the course of history, nationally or internationally."],
        ["Scope of impact", "20%", "From local to global reach."],
        ["Consequences", "15%", "Political, social, or economic consequences."],
        ["Influence on later events", "15%", "How much it helps explain what came after."],
        ["Scale and duration", "10%", "Size of the event and how long it lasted."],
        ["Media attention", "5%", "Coverage it received at the time — never decisive."],
        ["Uniqueness", "5%", "A one-of-a-kind event versus a recurring one."],
      ]
    : [
        ["Impacto histórico", "30%", "Grau de influência no curso da História, a nível nacional ou internacional."],
        ["Dimensão do impacto", "20%", "Do impacto local ao impacto internacional."],
        ["Consequências", "15%", "Consequências políticas, sociais ou económicas."],
        ["Relevância posterior", "15%", "O quanto ajuda a compreender os acontecimentos seguintes."],
        ["Dimensão e duração", "10%", "Dimensão do acontecimento e quanto durou."],
        ["Relevância mediática", "5%", "Cobertura que recebeu na época — nunca decisiva."],
        ["Singularidade", "5%", "Acontecimento único em vez de recorrente."],
      ];
  container.innerHTML = `
    <div class="relevance-doc-head">
      <p class="eyebrow">${escapeHtml(t("relevanceEyebrow"))}</p>
      <h2>${escapeHtml(t("relevanceDocTitle"))}</h2>
      <p>${escapeHtml(t("relevanceDocLead"))}</p>
    </div>
    <div class="relevance-doc-grid">
      <div class="relevance-doc-card">
        <h3>${escapeHtml(t("relevanceDocCriteriaTitle"))}</h3>
        <table class="relevance-criteria">
          <tbody>
            ${criteria.map(([label, weight, description]) => `
              <tr>
                <th scope="row">${escapeHtml(label)}</th>
                <td class="weight">${escapeHtml(weight)}</td>
                <td class="description">${escapeHtml(description)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
        <h3>${escapeHtml(t("relevanceDocHow"))}</h3>
        <p>${escapeHtml(t("relevanceDocHowBody"))}</p>
        <h3>${escapeHtml(t("relevanceDocMedia"))}</h3>
        <p>${escapeHtml(t("relevanceDocMediaBody"))}</p>
        <h3>${escapeHtml(t("relevanceDocLandmark"))}</h3>
        <p>${escapeHtml(t("relevanceDocLandmarkBody"))}</p>
        <h3>${escapeHtml(t("relevanceDocCuration"))}</h3>
        <p>${escapeHtml(t("relevanceDocCurationBody"))}</p>
      </div>
      <div class="relevance-doc-card example">
        <h3>${escapeHtml(t("relevanceDocExampleTitle"))}</h3>
        <div class="relevance-example">
          ${relevanceBadge({ relevance_level: 1 })}
          <h4>${escapeHtml(t("relevanceDocExampleHeadline"))}</h4>
          <p>${escapeHtml(t("relevanceDocExampleBody"))}</p>
        </div>
        <p class="relevance-scores-note">${escapeHtml(t("relevanceDocScoresNote"))}</p>
        <div class="relevance-level-legend">
          ${levels.map((info) => `
            <span class="relevance-badge relevance-level-${info.level}" tabindex="0" role="button" aria-describedby="relevance-tooltip">
              ${RELEVANCE_ICONS[info.level]}<span class="relevance-badge-name">${escapeHtml(info.name)}</span>
            </span>
          `).join("")}
        </div>
      </div>
    </div>`;
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
  renderHomeSections();
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
    readCalendarStateFromLocation();
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
  // URL limpo com qualquer profundidade (noticia/AAAA/MM/DD/slug-d8) ou alias.
  if (pathname.match(/\/noticia(?:\/.+)?\/?$/)) return "news";
  return "home";
}

const HERO_SLIDE_MS = 5200;

function startCarousel() {
  const dots = document.getElementById("hero-dots");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let slideStartedAt = performance.now();
  let timerFrame = null;

  const tick = (now) => {
    const progress = Math.min(1, (now - slideStartedAt) / HERO_SLIDE_MS);
    // O ponto do destaque ativo enche-se de cinzento no sentido dos ponteiros.
    dots?.querySelector(".hero-dot.active")?.style.setProperty("--p", String(progress));
    timerFrame = window.requestAnimationFrame(tick);
  };
  if (!reduceMotion) {
    timerFrame = window.requestAnimationFrame(tick);
  } else {
    dots?.querySelector(".hero-dot.active")?.style.setProperty("--p", "0");
  }

  const moveTo = (index) => {
    const items = state.data?.carousel || [];
    if (!items.length) return;
    state.slide = (index + items.length) % items.length;
    slideStartedAt = performance.now();
    renderHero();
  };
  const next = () => moveTo(state.slide + 1);
  const restartTimer = () => {
    clearInterval(state.timer);
    state.timer = setInterval(next, HERO_SLIDE_MS);
    slideStartedAt = performance.now();
  };
  clearInterval(state.timer);
  state.timer = setInterval(next, HERO_SLIDE_MS);
  document.getElementById("hero-next-slide")?.addEventListener("click", () => {
    next();
    restartTimer();
  });
  document.getElementById("hero-prev-slide")?.addEventListener("click", () => {
    moveTo(state.slide - 1);
    restartTimer();
  });
  dots?.addEventListener("click", (event) => {
    const dot = event.target.closest("[data-hero-dot]");
    if (!dot) return;
    moveTo(Number(dot.dataset.heroDot));
    restartTimer();
  });
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
    if (route === "calendar") state.calendarPickerVisible = true;
    if (route === "topics") loadTopicStateFromLocation();
    setRoute(route);
    if (route === "topics" && state.topicQuery && !state.topicResultSets.length) runTopicSearch(false);
  });

  // Ligações de navegação fora do menu principal (rodapé, botões internos).
  const routePaths = { home: "inicio", calendar: "calendario", topics: "temas", docs: "documentacao" };
  document.querySelectorAll("[data-route-link]").forEach((element) => {
    element.addEventListener("click", (event) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const route = element.dataset.routeLink;
      const path = routePaths[route];
      if (!path) return;
      event.preventDefault();
      history.pushState({}, "", routeUrl(path));
      setRoute(route);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
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
  // Granularidade: bloqueada mostra a razão; desbloqueada re-corre a análise.
  const hint = document.getElementById("topic-granularity-hint");
  for (const button of document.querySelectorAll("[data-topic-granularity]")) {
    button.addEventListener("click", (event) => {
      if (button.dataset.locked === "1") {
        event.preventDefault();
        hint.textContent = t("topicGranularityLocked");
        hint.hidden = false;
        return;
      }
      state.topicGranularity = button.dataset.topicGranularity;
      renderTopicGranularity();
      runTopicSearch(true);
    });
  }
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

// Parâmetros do calendário persistidos no URL.
function calendarUrlParams(dateValue) {
  return {
    data: dateValue,
    ...(state.calendarFormat !== "month" ? { formato: state.calendarFormat } : {}),
    ...(state.calendarView !== "onthisday" ? { vista: state.calendarView } : {}),
    ...(state.calendarSource ? { fonte: state.calendarSource } : {}),
  };
}

function readCalendarStateFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const format = params.get("formato");
  if (format === "week" || format === "month") state.calendarFormat = format;
  const view = params.get("vista");
  if (view === "exact" || view === "onthisday") state.calendarView = view;
  state.calendarSource = params.get("fonte") || "";
}

function setCalendarPeriod(patch = {}) {
  if (patch.formato && ["month", "week"].includes(patch.formato)) state.calendarFormat = patch.formato;
  if (patch.vista && ["onthisday", "exact"].includes(patch.vista)) state.calendarView = patch.vista;
  if ("fonte" in patch) state.calendarSource = patch.fonte || "";
  history.pushState({}, "", routeUrl("calendario", calendarUrlParams(state.selectedDate)));
  renderCalendarNavigation();
  renderCalendarGrid();
  renderDayPanel();
}

function applyCalendarDate(dateValue) {
  if (!isValidIsoDate(dateValue)) return;
  state.selectedDate = dateValue;
  state.calendarYear = dateYear(dateValue);
  state.calendarMonth = Number(dateValue.slice(5, 7));
  state.calendarPickerVisible = true;
  history.pushState({}, "", routeUrl("calendario", calendarUrlParams(dateValue)));
  setRoute("calendar");
}

function wireCalendar() {
  const selectCalendarDate = applyCalendarDate;

  document.getElementById("calendar-grid")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-date]");
    if (!button) return;
    selectCalendarDate(button.dataset.date);
  });

  const shiftMonth = (delta) => {
    const date = new Date(state.calendarYear, state.calendarMonth - 1 + delta, 1);
    state.calendarYear = date.getFullYear();
    state.calendarMonth = date.getMonth() + 1;
    // Em vista semana, o mês muda junto com a semana visível.
    if (state.calendarFormat === "week") {
      const { start } = weekRangeFor(state.selectedDate);
      const shifted = new Date(dateYear(start), Number(start.slice(5, 7)) - 1, Number(start.slice(8, 10)));
      shifted.setDate(shifted.getDate() + delta * 7);
      applyCalendarDate(isoDate(shifted.getFullYear(), shifted.getMonth() + 1, shifted.getDate()));
      return;
    }
    renderCalendarNavigation();
    renderCalendarGrid();
    renderDayPanel();
  };
  const shiftWeek = (delta) => {
    const { start } = weekRangeFor(state.selectedDate);
    const shifted = new Date(dateYear(start), Number(start.slice(5, 7)) - 1, Number(start.slice(8, 10)));
    shifted.setDate(shifted.getDate() + delta * 7);
    applyCalendarDate(isoDate(shifted.getFullYear(), shifted.getMonth() + 1, shifted.getDate()));
  };
  document.getElementById("calendar-prev-month")?.addEventListener("click", () => {
    if (state.calendarFormat === "week") shiftWeek(-1);
    else shiftMonth(-1);
  });
  document.getElementById("calendar-next-month")?.addEventListener("click", () => {
    if (state.calendarFormat === "week") shiftWeek(1);
    else shiftMonth(1);
  });
  document.getElementById("calendar-month-button")?.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleMonthPopover(document.getElementById("calendar-month-button"));
  });
  document.getElementById("calendar-date-button")?.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleDatePopover(document.getElementById("calendar-date-button"));
  });
  // Controlos de formato (Mês | Semana) e vista (Notícias de Ontem | Dia exato).
  for (const button of document.querySelectorAll("[data-calendar-format]")) {
    button.addEventListener("click", () => setCalendarPeriod({ formato: button.dataset.calendarFormat }));
  }
  for (const button of document.querySelectorAll("[data-calendar-view]")) {
    button.addEventListener("click", () => setCalendarPeriod({ vista: button.dataset.calendarView }));
  }
  // Filtro de jornais (finalmente ligado) — persiste no URL.
  document.getElementById("calendar-source")?.addEventListener("change", (event) => {
    setCalendarPeriod({ fonte: event.target.value });
  });
}

let activeCalendarPopover = null;

function closeCalendarPopovers() {
  activeCalendarPopover?.remove();
  activeCalendarPopover = null;
  document.getElementById("calendar-month-button")?.setAttribute("aria-expanded", "false");
  document.getElementById("calendar-date-button")?.setAttribute("aria-expanded", "false");
}

function openCalendarPopover(anchor, content, onSelect) {
  closeCalendarPopovers();
  const popover = document.createElement("div");
  popover.className = "calendar-popover";
  popover.innerHTML = content;
  document.body.appendChild(popover);
  activeCalendarPopover = popover;
  anchor.setAttribute("aria-expanded", "true");
  const width = Math.min(320, window.innerWidth - 24);
  const height = popover.offsetHeight || 360;
  if (window.innerWidth <= 768) {
    // Em ecrãs estreitos o popover fica centrado, abaixo da barra dos meses.
    const panel = document.getElementById("calendar-picker-panel");
    const panelRect = panel?.getBoundingClientRect();
    popover.style.left = `${(window.innerWidth - width) / 2}px`;
    popover.style.top = panelRect
      ? `${Math.max(12, panelRect.bottom + 10)}px`
      : `${(window.innerHeight - height) / 2}px`;
  } else {
    // No PC abre sempre abaixo (ou acima, se não couber) do botão — nunca a
    // sobrepor a fila dos botões.
    const rect = anchor.getBoundingClientRect();
    const left = Math.min(Math.max(rect.left, 12), window.innerWidth - width - 12);
    const below = rect.bottom + 8;
    let top = below;
    if (top + height > window.innerHeight - 8) {
      const above = rect.top - height - 8;
      top = above >= 12 ? above : Math.max(12, window.innerHeight - height - 12);
    }
    popover.style.left = `${left}px`;
    popover.style.top = `${top}px`;
  }
  popover.addEventListener("click", (event) => {
    const target = event.target.closest("[data-value]");
    if (!target) return;
    const value = target.dataset.value;
    closeCalendarPopovers();
    onSelect(value);
  });
}

function toggleMonthPopover(anchor) {
  if (activeCalendarPopover) {
    closeCalendarPopovers();
    return;
  }
  const cells = Array.from({ length: 12 }, (_, index) => `
    <button type="button" data-value="${index + 1}" class="${index + 1 === state.calendarMonth ? "selected" : ""}">${escapeHtml(monthName(index))}</button>
  `).join("");
  const content = `
    <div class="calendar-popover-year">
      <button type="button" data-year-step="-1" aria-label="Ano anterior">‹</button>
      <strong>${state.calendarYear}</strong>
      <button type="button" data-year-step="1" aria-label="Ano seguinte">›</button>
    </div>
    <div class="calendar-popover-grid">${cells}</div>
  `;
  openCalendarPopover(anchor, content, (value) => {
    state.calendarMonth = Math.min(Math.max(Number(value), 1), 12);
    renderCalendarNavigation();
    renderCalendarGrid();
    renderDayPanel();
  });
  activeCalendarPopover.querySelectorAll("[data-year-step]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      state.calendarYear += Number(button.dataset.yearStep);
      closeCalendarPopovers();
      renderCalendarNavigation();
      renderCalendarGrid();
      renderDayPanel();
      toggleMonthPopover(anchor);
    });
  });
}

function toggleDatePopover(anchor) {
  if (activeCalendarPopover) {
    closeCalendarPopovers();
    return;
  }
  let viewYear = state.calendarYear;
  let viewMonth = state.calendarMonth;

  const render = () => {
    const firstDay = new Date(viewYear, viewMonth - 1, 1);
    const daysInMonth = new Date(viewYear, viewMonth, 0).getDate();
    const offset = (firstDay.getDay() + 6) % 7;
    const postDates = new Set(state.data?.calendar?.post_dates || []);
    const recommendationDays = state.data?.calendar?.recommendations_by_day || {};
    const weekdayLabels = state.lang === "pt"
      ? ["S", "T", "Q", "Q", "S", "S", "D"]
      : ["M", "T", "W", "T", "F", "S", "S"];
    let cells = weekdayLabels.map((label) => `<span class="popover-weekday">${escapeHtml(label)}</span>`).join("");
    for (let i = 0; i < offset; i += 1) cells += "<span></span>";
    for (let day = 1; day <= daysInMonth; day += 1) {
      const dateValue = isoDate(viewYear, viewMonth, day);
      const hasPosts = postDates.has(dateValue) || postDates.has(isoDate(viewYear - 1, viewMonth, day));
      const hasRecommendations = Boolean(recommendationDays[monthDay(dateValue)]?.length);
      cells += `<button type="button" data-value="${dateValue}" class="${dateValue === state.selectedDate ? "selected" : ""}${hasPosts || hasRecommendations ? " has-posts" : ""}">${day}</button>`;
    }
    popoverBody.innerHTML = `
      <div class="calendar-popover-year">
        <button type="button" data-month-step="-1" aria-label="Mês anterior">‹</button>
        <strong>${escapeHtml(monthName(viewMonth - 1))} ${viewYear}</strong>
        <button type="button" data-month-step="1" aria-label="Mês seguinte">›</button>
      </div>
      <div class="calendar-popover-days">${cells}</div>
    `;
  };

  openCalendarPopover(anchor, '<div class="calendar-popover-body"></div>', (value) => {
    applyCalendarDate(value);
  });
  const popoverBody = activeCalendarPopover.querySelector(".calendar-popover-body");
  render();
  popoverBody.querySelectorAll("[data-value]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      closeCalendarPopovers();
      applyCalendarDate(button.dataset.value);
    });
  });
  popoverBody.querySelectorAll("[data-month-step]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const date = new Date(viewYear, viewMonth - 1 + Number(button.dataset.monthStep), 1);
      viewYear = date.getFullYear();
      viewMonth = date.getMonth() + 1;
      render();
    });
  });
}

document.addEventListener("pointerdown", (event) => {
  if (!activeCalendarPopover) return;
  if (event.target.closest(".calendar-popover")) return;
  if (event.target.closest("#calendar-month-button, #calendar-date-button")) return;
  closeCalendarPopovers();
});
// Deslizar a página também fecha os popovers.
document.addEventListener("scroll", () => closeCalendarPopovers(), { passive: true, capture: true });

// ---- Tooltip dos badges de relevância -------------------------------------
let relevanceTooltipElement = null;

function relevanceTooltipText(level) {
  const table = RELEVANCE_LEVELS[state.lang === "en" ? "en" : "pt"] || RELEVANCE_LEVELS.pt;
  const info = table.find((entry) => entry.level === Number(level));
  if (!info) return "";
  let html = `<strong>${info.name}</strong><span>${info.tooltip}</span>`;
  return html;
}

function showRelevanceTooltipRaw(badge, rawText) {
  hideRelevanceTooltip();
  if (!rawText) return;
  const tooltip = document.createElement("div");
  tooltip.id = "relevance-tooltip";
  tooltip.className = "relevance-tooltip relevance-generic";
  tooltip.setAttribute("role", "tooltip");
  tooltip.innerHTML = `<strong>${escapeHtml(t("topicGranularityLabel"))}</strong><span>${escapeHtml(rawText)}</span>`;
  document.body.appendChild(tooltip);
  relevanceTooltipElement = tooltip;
  const badgeRect = badge.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  let left = badgeRect.left + badgeRect.width / 2 - tooltipRect.width / 2;
  left = Math.max(10, Math.min(left, window.innerWidth - tooltipRect.width - 10));
  let top = badgeRect.top - tooltipRect.height - 10;
  if (top < 10) top = badgeRect.bottom + 10;
  tooltip.style.left = `${Math.round(left)}px`;
  tooltip.style.top = `${Math.round(top)}px`;
  tooltip.classList.add("visible");
}

function showRelevanceTooltip(badge) {
  hideRelevanceTooltip();
  const level = badge.getAttribute("data-relevance-level");
  const text = relevanceTooltipText(level);
  if (!text) return;
  const tooltip = document.createElement("div");
  tooltip.id = "relevance-tooltip";
  tooltip.className = `relevance-tooltip relevance-level-${level}`;
  tooltip.setAttribute("role", "tooltip");
  tooltip.innerHTML = text;
  document.body.appendChild(tooltip);
  relevanceTooltipElement = tooltip;
  const badgeRect = badge.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  let left = badgeRect.left + badgeRect.width / 2 - tooltipRect.width / 2;
  left = Math.max(10, Math.min(left, window.innerWidth - tooltipRect.width - 10));
  let top = badgeRect.top - tooltipRect.height - 10;
  if (top < 10) top = badgeRect.bottom + 10;
  tooltip.style.left = `${Math.round(left)}px`;
  tooltip.style.top = `${Math.round(top)}px`;
  tooltip.classList.add("visible");
}

function hideRelevanceTooltip() {
  if (relevanceTooltipElement) {
    relevanceTooltipElement.remove();
    relevanceTooltipElement = null;
  }
}

function wireRelevanceTooltips() {
  const target = (event) => event.target.closest?.(".relevance-badge, [data-tip]");
  const tipFor = (element) => (element.dataset.tip ? element.dataset.tip : relevanceTooltipText(element.dataset.relevanceLevel));
  const show = (element) => {
    if (element.dataset.tip) {
      showRelevanceTooltipRaw(element, element.dataset.tip);
    } else {
      showRelevanceTooltip(element);
    }
  };
  document.addEventListener("pointerenter", (event) => {
    const badge = target(event);
    if (badge) show(badge);
  }, true);
  document.addEventListener("pointerleave", (event) => {
    if (target(event)) hideRelevanceTooltip();
  }, true);
  document.addEventListener("focusin", (event) => {
    const badge = target(event);
    if (badge) show(badge);
  });
  document.addEventListener("focusout", (event) => {
    if (target(event)) hideRelevanceTooltip();
  });
  // Toque em mobile: primeiro toque abre, toque fora fecha.
  document.addEventListener("click", (event) => {
    const badge = target(event);
    if (badge) {
      event.preventDefault();
      event.stopPropagation();
      show(badge);
    } else {
      hideRelevanceTooltip();
    }
  });
  document.addEventListener("scroll", hideRelevanceTooltip, { passive: true, capture: true });
}

// Rodapé: voltar ao topo (botão na grelha + botão flutuante ao deslizar).
function wireFooter() {
  const scrollToTop = () => window.scrollTo({ top: 0, behavior: "smooth" });
  document.getElementById("footer-back-top")?.addEventListener("click", scrollToTop);
  const floating = document.getElementById("back-top-floating");
  floating?.addEventListener("click", scrollToTop);
  if (!floating) return;
  const updateVisibility = () => {
    floating.hidden = window.scrollY < 480;
  };
  window.addEventListener("scroll", updateVisibility, { passive: true });
  updateVisibility();
}

async function init() {
  wireNavigation();
  wireCalendar();
  wireLanguageSwitch();
  wireStoryLinks();
  wireTopics();
  wireRelevanceTooltips();
  wireFooter();
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
  if (initialRoute === "topics" && state.topicQuery && !state.topicResultSets.length) runTopicSearch(false);
  startCarousel();
  const footerInstagram = document.getElementById("footer-instagram");
  const profileUrl = cleanProfileUrl(state.data?.instagram_profile_url);
  if (footerInstagram && profileUrl) footerInstagram.href = profileUrl;
}

function cleanProfileUrl(value) {
  const url = String(value || "").trim();
  return url && /^https:\/\//.test(url) ? url : "";
}

init();
