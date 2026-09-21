/**
 * OJ Microline schedule card.
 *
 * Shows the weekly schedule of an OJ Microline (WD5-series) thermostat from
 * its schedule sensor, highlighting the event that is active right now.
 * Bundled with and loaded by the OJ Microline Thermostat integration.
 *
 *   type: custom:ojmicroline-schedule-card
 *   entity: sensor.bathroom_schedule
 *   title: Bathroom   # optional
 */

const DAYS = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
];
const DAY_SECONDS = 86400;
// 2024-01-01 was a Monday; used to get localized weekday names.
const MONDAY = Date.UTC(2024, 0, 1, 12);

const TEXTS = {
  en: { now: "Now", noSchedule: "No schedule", missing: "Entity not found" },
  nl: { now: "Nu", noSchedule: "Geen schema", missing: "Entiteit niet gevonden" },
  pt: { now: "Agora", noSchedule: "Sem horário", missing: "Entidade não encontrada" },
};

const escapeHtml = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );

const toSeconds = (event) => {
  const [hours, minutes] = event.time.split(":").map(Number);
  return hours * 3600 + minutes * 60 + (event.next_day ? DAY_SECONDS : 0);
};

class OJMicrolineScheduleCard extends HTMLElement {
  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: {
            entity: { domain: "sensor", integration: "ojmicroline_thermostat" },
          },
        },
        { name: "title", selector: { text: {} } },
      ],
    };
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (entityId) =>
        entityId.startsWith("sensor.") &&
        entityId.endsWith("_schedule") &&
        Array.isArray(hass.states[entityId].attributes.monday),
    );
    return { entity: entity || "" };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Please define an entity");
    }
    this._config = config;
    this._key = undefined;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    // The highlighted event depends on the time, so also re-render when the
    // minute changes, not only when the sensor does.
    const state = hass.states[this._config.entity];
    const key = [
      state && state.last_updated,
      hass.locale && hass.locale.language,
      Math.floor(Date.now() / 60000),
    ].join("|");
    if (key !== this._key) {
      this._key = key;
      this._render();
    }
  }

  getCardSize() {
    return 5;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  connectedCallback() {
    this._timer = setInterval(() => {
      if (this._hass) this.hass = this._hass;
    }, 60000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  _language() {
    return (
      (this._hass && ((this._hass.locale && this._hass.locale.language) || this._hass.language)) ||
      "en"
    );
  }

  _texts() {
    return TEXTS[this._language().split("-")[0]] || TEXTS.en;
  }

  _dayNames() {
    const format = new Intl.DateTimeFormat(this._language(), {
      weekday: "short",
      timeZone: "UTC",
    });
    return DAYS.map((_, index) => format.format(new Date(MONDAY + index * DAY_SECONDS * 1000)));
  }

  _formatTemperature(value) {
    return `${new Intl.NumberFormat(this._language(), { maximumFractionDigits: 1 }).format(value)}°`;
  }

  /** Return [dayIndex, eventIndex] of the event that is active now. */
  _activeEvent(schedule, now) {
    const today = (now.getDay() + 6) % 7;
    const yesterday = (today + 6) % 7;
    const nowSeconds = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();
    let active = null;
    let activeSeconds = -Infinity;
    for (const [day, offset] of [
      [yesterday, -DAY_SECONDS],
      [today, 0],
    ]) {
      (schedule[DAYS[day]] || []).forEach((event, index) => {
        const seconds = toSeconds(event) + offset;
        if (seconds <= nowSeconds && seconds >= activeSeconds) {
          active = [day, index];
          activeSeconds = seconds;
        }
      });
    }
    return active;
  }

  _render() {
    if (!this._config) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });

    const texts = this._texts();
    const state = this._hass && this._hass.states[this._config.entity];
    const title =
      this._config.title !== undefined
        ? this._config.title
        : state
          ? (state.attributes.friendly_name || "").replace(/ schedule$/i, "")
          : "";

    let current = "";
    let body = "";
    if (!this._hass) {
      body = "";
    } else if (!state) {
      body = `<div class="message">${escapeHtml(texts.missing)}: ${escapeHtml(this._config.entity)}</div>`;
    } else if (!Array.isArray(state.attributes.monday)) {
      body = `<div class="message">${escapeHtml(texts.noSchedule)}</div>`;
    } else {
      const now = new Date();
      const today = (now.getDay() + 6) % 7;
      const active = this._activeEvent(state.attributes, now);
      const names = this._dayNames();
      const rows = DAYS.map((day, dayIndex) => {
        const events = (state.attributes[day] || [])
          .map((event, index) => {
            const isActive = active && active[0] === dayIndex && active[1] === index;
            return `<span class="event${isActive ? " active" : ""}">
              <span class="time">${escapeHtml(event.time)}${event.next_day ? "<sup>+1</sup>" : ""}</span>
              <span class="temp">${escapeHtml(this._formatTemperature(event.temperature))}</span>
            </span>`;
          })
          .join("");
        return `<div class="row${dayIndex === today ? " today" : ""}">
          <div class="day">${escapeHtml(names[dayIndex])}</div>
          <div class="events">${events}</div>
        </div>`;
      }).join("");
      if (active) {
        const temperature = state.attributes[DAYS[active[0]]][active[1]].temperature;
        current = `<div class="now">${escapeHtml(texts.now)}: <b>${escapeHtml(this._formatTemperature(temperature))}</b></div>`;
      }
      body = `<div class="rows">${rows}</div>`;
    }

    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 16px; cursor: pointer; }
        .header { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 12px; }
        .title { font-size: 1.2em; font-weight: 500; color: var(--primary-text-color); }
        .now { color: var(--secondary-text-color); white-space: nowrap; }
        .now b { color: var(--primary-text-color); }
        .rows { display: flex; flex-direction: column; gap: 4px; }
        .row { display: flex; align-items: center; gap: 8px; padding: 4px 6px; border-radius: 8px; }
        .row.today { background: var(--secondary-background-color); }
        .day { width: 2.8em; flex: none; color: var(--secondary-text-color); text-transform: capitalize; }
        .row.today .day { color: var(--primary-text-color); font-weight: 500; }
        .events { display: flex; flex-wrap: wrap; gap: 4px; }
        .event { display: inline-flex; gap: 4px; padding: 2px 8px; border-radius: 12px;
          border: 1px solid var(--divider-color); font-size: 0.9em; line-height: 1.6; }
        .event .time { color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
        .event .temp { color: var(--primary-text-color); font-weight: 500; }
        .event.active { background: var(--primary-color); border-color: var(--primary-color); }
        .event.active .time, .event.active .temp { color: var(--text-primary-color, #fff); }
        sup { font-size: 0.7em; }
        .message { color: var(--secondary-text-color); }
      </style>
      <ha-card>
        <div class="header">
          <div class="title">${escapeHtml(title)}</div>
          ${current}
        </div>
        ${body}
      </ha-card>`;

    this.shadowRoot.querySelector("ha-card").onclick = () => {
      this.dispatchEvent(
        new CustomEvent("hass-more-info", {
          detail: { entityId: this._config.entity },
          bubbles: true,
          composed: true,
        }),
      );
    };
  }
}

if (!customElements.get("ojmicroline-schedule-card")) {
  customElements.define("ojmicroline-schedule-card", OJMicrolineScheduleCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "ojmicroline-schedule-card",
    name: "OJ Microline schedule",
    description: "The weekly schedule of an OJ Microline thermostat.",
    preview: true,
    documentationURL:
      "https://github.com/laurensdehoorne/home-assistant-ojmicroline-thermostat",
  });
}
