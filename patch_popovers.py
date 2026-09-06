"""Substitui os seletores nativos do calendário por popovers personalizados."""
from pathlib import Path

p = Path("site/app.js")
t = p.read_text(encoding="utf-8")

old = '''function renderCalendarNavigation() {
  const picker = document.getElementById("calendar-date-picker");
  const source = document.getElementById("calendar-source");
  const largePicker = document.getElementById("calendar-picker-panel");
  if (picker) picker.value = state.selectedDate;
  if (largePicker) largePicker.hidden = !state.calendarPickerVisible;
  if (!source) return;'''
new = '''function renderCalendarNavigation() {
  const source = document.getElementById("calendar-source");
  const largePicker = document.getElementById("calendar-picker-panel");
  if (largePicker) largePicker.hidden = !state.calendarPickerVisible;
  setText("#calendar-month-label", monthName(state.calendarMonth - 1));
  setText("#calendar-year-label", String(state.calendarYear));
  setText("#calendar-date-label", formatDate(state.selectedDate));
  if (!source) return;'''
assert old in t, "nav"
t = t.replace(old, new, 1)

old_opts = '''function renderCalendarMonthOptions() {
  const select = document.getElementById("calendar-month");
  if (!select) return;
  select.innerHTML = Array.from({ length: 12 }, (_, index) => {
    const value = index + 1;
    return `<option value="${value}" ${value === state.calendarMonth ? "selected" : ""}>${escapeHtml(monthName(index))}</option>`;
  }).join("");
}

'''
assert old_opts in t, "month options"
t = t.replace(old_opts, "", 1)

old_grid_call = '''  renderCalendarMonthOptions();
  yearInput.value = state.calendarYear;

  const firstDay'''
assert old_grid_call in t, "grid call"
t = t.replace(old_grid_call, new_grid_call := "  const firstDay", 1)

old_grid_head = '''function renderCalendarGrid() {
  const grid = document.getElementById("calendar-grid");
  const yearInput = document.getElementById("calendar-year");
  if (!grid || !yearInput) return;
'''
new_grid_head = '''function renderCalendarGrid() {
  const grid = document.getElementById("calendar-grid");
  if (!grid) return;
'''
assert old_grid_head in t, "grid head"
t = t.replace(old_grid_head, new_grid_head, 1)

old_wire = '''  document.getElementById("calendar-year")?.addEventListener("change", (event) => {
    const year = Number(event.target.value);
    if (!Number.isFinite(year)) return;
    state.calendarYear = Math.min(Math.max(Math.trunc(year), 1996), 2050);
    renderCalendarGrid();
    renderDayPanel();
  });

  document.getElementById("calendar-month")?.addEventListener("change", (event) => {
    const month = Number(event.target.value);
    if (!Number.isFinite(month)) return;
    state.calendarMonth = Math.min(Math.max(Math.trunc(month), 1), 12);
    renderCalendarGrid();
    renderDayPanel();
  });

  const shiftMonth = (delta) => {
    const date = new Date(state.calendarYear, state.calendarMonth - 1 + delta, 1);
    state.calendarYear = date.getFullYear();
    state.calendarMonth = date.getMonth() + 1;
    renderCalendarGrid();
    renderDayPanel();
  };
  document.getElementById("calendar-prev-month")?.addEventListener("click", () => shiftMonth(-1));
  document.getElementById("calendar-next-month")?.addEventListener("click", () => shiftMonth(1));
  document.getElementById("calendar-date-picker")?.addEventListener("change", (event) => {
    selectCalendarDate(event.target.value);
  });
  document.getElementById("calendar-source")?.addEventListener("change", (event) => {
    state.calendarSource = event.target.value;
    renderDayPanel();
    loadCalendarRecommendations();
  });
}'''
new_wire = '''  const shiftMonth = (delta) => {
    const date = new Date(state.calendarYear, state.calendarMonth - 1 + delta, 1);
    state.calendarYear = date.getFullYear();
    state.calendarMonth = date.getMonth() + 1;
    renderCalendarNavigation();
    renderCalendarGrid();
    renderDayPanel();
  };
  document.getElementById("calendar-prev-month")?.addEventListener("click", () => shiftMonth(-1));
  document.getElementById("calendar-next-month")?.addEventListener("click", () => shiftMonth(1));
  document.getElementById("calendar-month-button")?.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleMonthPopover(document.getElementById("calendar-month-button"));
  });
  document.getElementById("calendar-date-button")?.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleDatePopover(document.getElementById("calendar-date-button"));
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
  const rect = anchor.getBoundingClientRect();
  const width = Math.min(320, window.innerWidth - 24);
  const left = Math.min(Math.max(rect.left, 12), window.innerWidth - width - 12);
  popover.style.left = `${left}px`;
  popover.style.top = `${Math.max(12, Math.min(rect.bottom + 8, window.innerHeight - 380))}px`;
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
  openCalendarPopover(anchor, content, () => {});
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

  openCalendarPopover(anchor, '<div class="calendar-popover-body"></div>', () => {});
  const popoverBody = activeCalendarPopover.querySelector(".calendar-popover-body");
  render();
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
});'''
assert old_wire in t, "wire"
t = t.replace(old_wire, new_wire, 1)

p.write_text(t, encoding="utf-8")
print("popovers implementados")
