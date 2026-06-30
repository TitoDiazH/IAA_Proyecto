const TERM_LABELS = {
  10: "Primer semestre",
  20: "Segundo semestre",
};

export function parsePeriod(period) {
  if (typeof period !== "string" || !/^\d{6}$/.test(period)) return null;
  return { year: parseInt(period.slice(0, 4), 10), term: period.slice(4, 6) };
}

export function formatPeriod(period) {
  const parsed = parsePeriod(period);
  if (!parsed) return period ?? "";
  const label = TERM_LABELS[parsed.term] || `Periodo ${parsed.term}`;
  return `${parsed.year} - ${label}`;
}

// direction: 1 to go forward, -1 to go backward
export function shiftPeriod(period, direction) {
  const parsed = parsePeriod(period);
  if (!parsed) return period;
  let { year, term } = parsed;
  if (direction > 0) {
    if (term === "10") term = "20";
    else {
      term = "10";
      year += 1;
    }
  } else {
    if (term === "20") term = "10";
    else {
      term = "20";
      year -= 1;
    }
  }
  return `${year}${term}`;
}

export function currentPeriod(date = new Date()) {
  const year = date.getFullYear();
  const term = date.getMonth() < 6 ? "10" : "20";
  return `${year}${term}`;
}
