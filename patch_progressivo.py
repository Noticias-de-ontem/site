"""Posicionamento do popover + gráfico progressivo + exportação só no fim."""
from pathlib import Path

# ---------- 1. app.js ----------
p = Path("site/app.js")
t = p.read_text(encoding="utf-8")

# 1a. posicionamento: mede a altura, abre abaixo; se não couber, abre acima
old_pos = '''  activeCalendarPopover = popover;
  anchor.setAttribute("aria-expanded", "true");
  const rect = anchor.getBoundingClientRect();
  const width = Math.min(320, window.innerWidth - 24);
  if (window.innerWidth <= 768) {
    // Em ecrãs estreitos o popover fica centrado e junto ao topo do painel.
    const panel = document.getElementById("calendar-picker-panel");
    const panelRect = panel?.getBoundingClientRect();
    popover.style.left = `${(window.innerWidth - width) / 2}px`;
    popover.style.top = panelRect
      ? `${Math.max(12, panelRect.top + 70)}px`
      : `${(window.innerHeight - 380) / 2}px`;
  } else {
    const rect = anchor.getBoundingClientRect();
    const left = Math.min(Math.max(rect.left, 12), window.innerWidth - width - 12);
    popover.style.left = `${left}px`;
    popover.style.top = `${Math.max(12, Math.min(rect.bottom + 8, window.innerHeight - 380))}px`;
  }'''
new_pos = '''  activeCalendarPopover = popover;
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
  }'''
assert old_pos in t, "pos"
t = t.replace(old_pos, new_pos, 1)

# 1b. fetchTopicSeries: callback onSeriesUpdate(year, entry) após cada ano
old_sig = '''async function fetchTopicSeries(query, source, fromDate, toDate, signal, onProgress = null) {'''
new_sig = '''async function fetchTopicSeries(query, source, fromDate, toDate, signal, onProgress = null, onSeriesUpdate = null) {'''
assert old_sig in t, "sig"
t = t.replace(old_sig, new_sig, 1)

old_done = '''      completed += 1;
      if (onProgress) onProgress(completed, slices.length, slice.year, "done");
    }
  };'''
new_done = '''      completed += 1;
      if (onProgress) onProgress(completed, slices.length, slice.year, "done");
      if (onSeriesUpdate) onSeriesUpdate(slice.year, results[index]);
    }
  };'''
assert old_done in t, "done"
t = t.replace(old_done, new_done, 1)

# 1c. runTopicSearch: esqueleto progressivo + render a cada ano concluído
old_init = '''      } else {
        results = new Array(analyses.length);
        let cursor = 0;
        const worker = async () => {'''
new_init = '''      } else {
        // Esqueleto com todos os anos a null: o gráfico nasce vazio e cresce
        // ano a ano à medida que cada contagem é verificada.
        results = analyses.map((analysis) => ({
          ...analysis,
          series: topicYearSlices(fromDate, toDate).map((slice) => ({
            year: slice.year,
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
        const worker = async () => {'''
assert old_init in t, "init"
t = t.replace(old_init, new_init, 1)

old_call = '''              result = await fetchTopicSeries(
                analysis.query,
                analysis.source,
                fromDate,
                toDate,
                searchAbort.signal,
                (done, total, year, phase) => {
                  if (phase === "start") {
                    // Mostra o ano em curso sem avançar o contador.
                    updateTopicProgress(completedPeriods, totalPeriods, year);
                    return;
                  }
                  completedPeriods += 1;
                  updateTopicProgress(completedPeriods, totalPeriods);
                },
              );'''
new_call = '''              const seriesIndex = index;
              result = await fetchTopicSeries(
                analysis.query,
                analysis.source,
                fromDate,
                toDate,
                searchAbort.signal,
                (done, total, year, phase) => {
                  if (phase === "start") {
                    // Mostra o ano em curso sem avançar o contador.
                    updateTopicProgress(completedPeriods, totalPeriods, year);
                    return;
                  }
                  completedPeriods += 1;
                  updateTopicProgress(completedPeriods, totalPeriods);
                },
                (year, entry) => {
                  // Cada ano verificado entra no gráfico imediatamente.
                  const resultSet = state.topicResultSets[seriesIndex];
                  const point = resultSet?.series?.find((item) => item.year === Number(year));
                  if (point) {
                    point.count = entry.count;
                    point.failed = entry.failed;
                    point.error_code = entry.error_code;
                    if (Number.isFinite(entry.count)) resultSet.total += entry.count;
                    renderTopicGraph();
                  }
                },
              );'''
assert old_call in t, "call"
t = t.replace(old_call, new_call, 1)

# 1d. renderTopicGraph: exportação só no fim; animação só fora do carregamento
old_foot = '''    <div class="topic-chart-footer">
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
  `;'''
new_foot = '''    ${state.topicLoading ? "" : `
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
  `;'''
assert old_foot in t, "footer"
t = t.replace(old_foot, new_foot, 1)

# classe loading no contentor (suprime a animação de desenho durante o crescimento)
old_container = '''  container.innerHTML = `
    <div class="topic-result-heading">'''
new_container = '''  container.classList.toggle("loading", Boolean(state.topicLoading));
  container.innerHTML = `
    <div class="topic-result-heading">'''
assert old_container in t, "container"
t = t.replace(old_container, new_container, 1)

p.write_text(t, encoding="utf-8")
print("app.js: gráfico progressivo + exportação no fim")

# ---------- 2. styles.css ----------
p = Path("site/styles.css")
t = p.read_text(encoding="utf-8")
old_css = """.chart-line {
  fill: none;
  stroke: var(--brand-deep);
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 3;
  /* Revelação ano a ano: a linha desenha-se e os pontos surgem em sequência. */
  stroke-dasharray: 1;
  stroke-dashoffset: 1;
  animation: chart-line-draw 1.6s ease-out forwards;
}"""
new_css = """.chart-line {
  fill: none;
  stroke: var(--brand-deep);
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 3;
  /* Revelação ano a ano: a linha desenha-se e os pontos surgem em sequência
     apenas na renderização final — durante a pesquisa o gráfico cresce sem
     repetir a animação. */
  stroke-dasharray: 1;
  stroke-dashoffset: 1;
  animation: chart-line-draw 1.6s ease-out forwards;
}

.topic-results.loading .chart-line {
  animation: none;
  stroke-dasharray: none;
  stroke-dashoffset: 0;
}

.topic-results.loading .chart-point,
.topic-results.loading .chart-value-label {
  animation: none;
  opacity: 1;
}"""
assert old_css in t, "css chart"
t = t.replace(old_css, new_css, 1)
p.write_text(t, encoding="utf-8")
print("css: crescimento sem repetir animação")
