import {
  AlertTriangle,
  ArrowLeft,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  Loader2,
  Quote,
  RefreshCcw,
} from "lucide-react";
import * as pdfjsLib from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { syllabusDownloadUrl, syllabusViewUrl } from "../api";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

const PDF_RENDER_SCALE = 1.08;

const HIGHLIGHT_COLORS = {
  critica: "rgba(198, 40, 40, 0.30)",
  crítica: "rgba(198, 40, 40, 0.30)",
  moderada: "var(--warning-bg)",
  menor: "rgba(37, 99, 235, 0.24)",
};

const SYLLABUS_LABELS = {
  evaluaciones: "Evaluaciones y Ponderaciones",
  evaluaciones_y_ponderaciones: "Evaluaciones y Ponderaciones",
  requisitos_aprobacion: "Requisitos de Aprobación",
  requisitos_exencion: "Requisitos de Exención",
  nota_final: "Nota Final",
  threshold: "Requisito de Exención",
  minimum_exam_grade: "Nota Mínima de Examen",
  minimum_final_grade: "Nota Mínima de Aprobación",
  automatic_failure_rules: "Reglas de Reprobación Automática",
  final_grade_formula: "Fórmula de Nota Final",
  evaluation_count: "Cantidad de Evaluaciones",
  evaluation_type: "Tipo de Evaluación",
  evaluation_weight: "Ponderación",
  evaluation_description: "Descripción de Evaluación",
  ponderaciones: "Ponderaciones",
};

// ─── Color palette for course cards ─────────────────────────────────────────
const PALETTE = [
  { bg: "#e8f5e9", border: "#66bb6a", accent: "#2e7d32" },
  { bg: "#e3f2fd", border: "#64b5f6", accent: "#1565c0" },
  { bg: "#fce4ec", border: "#f48fb1", accent: "#880e4f" },
  { bg: "#fff8e1", border: "#ffca28", accent: "#e65100" },
  { bg: "#f3e5f5", border: "#ce93d8", accent: "#4a148c" },
  { bg: "#e0f7fa", border: "#4dd0e1", accent: "#006064" },
  { bg: "#f9fbe7", border: "#aed581", accent: "#33691e" },
  { bg: "#fbe9e7", border: "#ff8a65", accent: "#bf360c" },
];

function courseColor(id) {
  return PALETTE[id % PALETTE.length];
}

function formatSyllabusLabel(value) {
  const rawValue = String(value || "").trim();
  if (!rawValue) return "Apartado no especificado";

  const key = rawValue
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");

  if (SYLLABUS_LABELS[key]) return SYLLABUS_LABELS[key];

  return rawValue
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

// ─── Shared: Severity badge ──────────────────────────────────────────────────
function SeverityBadge({ severity }) {
  const cls = `severity severity-${severity?.toLowerCase() || "none"}`;
  return <span className={cls}>{severity || "Sin nivel"}</span>;
}

function formatFileSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "PDF";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatEvaluationEvidence(row) {
  const parts = [];
  if (row.tipo) parts.push(row.tipo);
  if (row.ponderacion !== null && row.ponderacion !== undefined) {
    parts.push(`${row.ponderacion}%`);
  }
  if (row.descripcion) parts.push(row.descripcion);
  return parts.join(" · ");
}

function normalizeEvaluationRow(value) {
  if (!value || typeof value !== "object") return null;

  const tipo = String(value.tipo || value.type || "").trim();
  const descripcion = String(value.descripcion || value.description || "").trim();
  const rawPonderacion = value.ponderacion ?? value.percentage ?? value.weight ?? null;
  const ponderacion =
    rawPonderacion === null || rawPonderacion === undefined || rawPonderacion === ""
      ? null
      : String(rawPonderacion).trim();

  if (!tipo && !descripcion && !ponderacion) return null;
  return { tipo, ponderacion, descripcion };
}

function parsePlainEvaluationEvidenceText(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed) return null;

  const match = trimmed.match(
    /^(?<tipo>.+?)\s+(?<ponderacion>\d+(?:[.,]\d+)?\s*%)\s+(?<descripcion>.+)$/
  );
  if (!match?.groups) return null;

  const tipo = match.groups.tipo.trim();
  const ponderacion = match.groups.ponderacion.trim();
  const descripcion = match.groups.descripcion.trim();
  if (!tipo || !ponderacion || !descripcion) return null;

  return [{ tipo, ponderacion, descripcion }];
}

function parseEvaluationEvidenceText(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed.startsWith("[") && !trimmed.startsWith("{")) {
    return parsePlainEvaluationEvidenceText(trimmed);
  }

  try {
    const parsed = JSON.parse(trimmed);
    const rows = Array.isArray(parsed) ? parsed : [parsed];
    const evaluationRows = rows.map(normalizeEvaluationRow).filter(Boolean);
    return evaluationRows.length ? evaluationRows : null;
  } catch {
    return null;
  }
}

function normalizeEvidence(evidence) {
  if (!evidence) return [];

  const items = Array.isArray(evidence)
    ? evidence
    : Array.isArray(evidence.items)
      ? evidence.items
      : [];

  return items
    .map((item) => {
      const rawText = String(item?.text || item?.quote || item?.citation || "").trim();
      const evaluationRows = parseEvaluationEvidenceText(rawText);
      return {
        nrc: String(item?.nrc || "").trim(),
        page: item?.page ?? null,
        pageNumbers: Array.isArray(item?.page_numbers)
          ? item.page_numbers
          : Array.isArray(item?.pageNumbers)
            ? item.pageNumbers
            : [],
        sourceId: item?.source_id || item?.sourceId || null,
        section: item?.section || null,
        fieldPath: item?.field_path || item?.fieldPath || null,
        matchStatus: item?.match_status || item?.matchStatus || "legacy",
        confidence: Number.isFinite(Number(item?.confidence))
          ? Number(item.confidence)
          : null,
        rects: Array.isArray(item?.rects) ? item.rects : [],
        text: evaluationRows
          ? evaluationRows.map(formatEvaluationEvidence).join(" | ")
          : rawText,
        matchText: rawText,
        evaluationRows,
      };
    })
    .filter((item) => item.nrc && item.text);
}

function normalizeSeverity(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized.startsWith("cr")) return "critica";
  if (normalized.startsWith("me")) return "menor";
  return "moderada";
}

function normalizeForMatch(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9%.,+=-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function collectReportHighlights(report) {
  if (!report?.inconsistencies?.length) return [];

  return report.inconsistencies.flatMap((item) => {
    const severity = normalizeSeverity(item.severity);
    return normalizeEvidence(item.evidence).map((quote, evidenceIndex) => ({
      ...quote,
      severity,
      color: HIGHLIGHT_COLORS[severity] || HIGHLIGHT_COLORS.moderada,
      section: item.section,
      variable: item.variable,
      inconsistencyId: item.id,
      evidenceIndex,
      highlightId: `${item.id}-${evidenceIndex}`,
    }));
  });
}

function evidenceStatusLabel(status) {
  if (status === "verified") return "Verificada";
  if (status === "approximate" || status === "source_resolved") return "Aproximada";
  if (status === "unverified") return "No verificada";
  return null;
}

function textItemToPartialRect(item, viewport, startRatio = 0, endRatio = 1) {
  const rect = textItemToRect(item, viewport);
  const clampedStart = Math.min(Math.max(startRatio, 0), 1);
  const clampedEnd = Math.min(Math.max(endRatio, clampedStart), 1);
  const left = rect.left + rect.width * clampedStart;
  const width = Math.max(rect.width * (clampedEnd - clampedStart), 4);
  return { ...rect, left, width };
}

function rectsForMatchedSpan(mappings, spanStart, spanEnd, pageNumber = null) {
  return mappings
    .map((mapping) => {
      if (pageNumber !== null && mapping.pageNumber !== pageNumber) return null;
      const overlapStart = Math.max(spanStart, mapping.start);
      const overlapEnd = Math.min(spanEnd, mapping.end);
      if (
        overlapEnd <= overlapStart ||
        !mapping.text.length ||
        !mapping.item ||
        !mapping.viewport
      ) {
        return null;
      }

      const localStart = overlapStart - mapping.start;
      const localEnd = overlapEnd - mapping.start;
      return textItemToPartialRect(
        mapping.item,
        mapping.viewport,
        localStart / mapping.text.length,
        localEnd / mapping.text.length
      );
    })
    .filter(Boolean);
}

function createSearchItems(pageSegments) {
  return pageSegments.flatMap((segment) =>
    segment.textItems.map((item, itemIndex) => ({
      item,
      itemIndex,
      pageNumber: segment.pageNumber,
      viewport: segment.viewport,
      text: normalizeForMatch(item.str),
    }))
  );
}

function findMatchingTextRectsInSegments(pageSegments, quoteText, pageNumber = null) {
  const quote = normalizeForMatch(quoteText);
  if (quote.length < 4) return [];

  const searchItems = createSearchItems(pageSegments);
  const itemTexts = searchItems.map((item) => item.text);

  for (let start = 0; start < itemTexts.length; start += 1) {
    let windowText = "";
    const mappings = [];

    for (let end = start; end < itemTexts.length && mappings.length < 80; end += 1) {
      const itemText = itemTexts[end];
      if (!itemText) continue;

      if (windowText) windowText += " ";
      const itemStart = windowText.length;
      windowText += itemText;
      const itemEnd = windowText.length;
      mappings.push({
        item: searchItems[end].item,
        itemIndex: searchItems[end].itemIndex,
        pageNumber: searchItems[end].pageNumber,
        viewport: searchItems[end].viewport,
        start: itemStart,
        end: itemEnd,
        text: itemText,
      });

      const matchStart = windowText.indexOf(quote);
      if (matchStart !== -1) {
        const rects = rectsForMatchedSpan(
          mappings,
          matchStart,
          matchStart + quote.length,
          pageNumber
        );
        if (rects.length) return rects;
      }

      if (windowText.length > quote.length * 1.8 + 40) {
        break;
      }
    }
  }

  for (let start = 0; start < itemTexts.length; start += 1) {
    let windowText = "";
    const mappings = [];

    for (let end = start; end < itemTexts.length && mappings.length < 80; end += 1) {
      const itemText = itemTexts[end];
      if (!itemText) continue;

      windowText = windowText ? `${windowText} ${itemText}` : itemText;
      mappings.push({
        item: searchItems[end].item,
        itemIndex: searchItems[end].itemIndex,
        pageNumber: searchItems[end].pageNumber,
        viewport: searchItems[end].viewport,
        start: Math.max(windowText.length - itemText.length, 0),
        end: windowText.length,
        text: itemText,
      });

      const enoughContext =
        windowText.length >= Math.min(Math.max(quote.length * 0.3, 12), 36);
      if (enoughContext && quote.includes(windowText)) {
        const rects = mappings
          .filter((mapping) => pageNumber === null || mapping.pageNumber === pageNumber)
          .filter((mapping) => mapping.item && mapping.viewport)
          .map((mapping) => textItemToRect(mapping.item, mapping.viewport));
        if (rects.length) return rects;
      }

      if (windowText.length > quote.length * 1.8 + 40) {
        break;
      }
    }
  }

  return [];
}

function rectsFromEvidence(highlight) {
  if (!highlight.rects?.length) return [];

  return highlight.rects
    .map((rect, index) => {
      const left = Number(rect.left ?? rect.x);
      const top = Number(rect.top ?? rect.y);
      const width = Number(rect.width ?? rect.w);
      const height = Number(rect.height ?? rect.h);
      if (![left, top, width, height].every(Number.isFinite) || width <= 0 || height <= 0) {
        return null;
      }
      return {
        left,
        top,
        width,
        height,
        color: highlight.color,
        severity: highlight.severity,
        title: `NRC ${highlight.nrc}: ${highlight.variable}`,
        isFocused: false,
        key: `${highlight.inconsistencyId}-rect-${index}`,
      };
    })
    .filter(Boolean);
}

function textItemToRect(item, viewport) {
  const transform = pdfjsLib.Util.transform(viewport.transform, item.transform);
  const height = Math.max(Math.abs(transform[3]), item.height * viewport.scale, 8);
  const width = Math.max(item.width * viewport.scale, 6);
  return {
    left: transform[4],
    top: transform[5] - height,
    width,
    height,
  };
}

function normalizeWeight(value) {
  const match = String(value || "").match(/\d+(?:[.,]\d+)?/);
  if (!match) return null;
  const parsed = Number.parseFloat(match[0].replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

function textHasWeight(text, expectedWeight) {
  if (!Number.isFinite(expectedWeight)) return false;
  const matches = String(text || "").match(/\d+(?:[.,]\d+)?\s*%?/g) || [];
  return matches.some((match) => {
    const parsed = normalizeWeight(match);
    return Number.isFinite(parsed) && Math.abs(parsed - expectedWeight) < 0.01;
  });
}

function hasMeaningfulTerm(rowText, value) {
  const term = normalizeForMatch(value);
  return term.length >= 3 && rowText.includes(term);
}

function evaluationRowScore(rowText, row) {
  const expectedWeight = normalizeWeight(row.ponderacion);
  const checks = [
    Boolean(row.tipo) && hasMeaningfulTerm(rowText, row.tipo),
    expectedWeight !== null && textHasWeight(rowText, expectedWeight),
    Boolean(row.descripcion) && hasMeaningfulTerm(rowText, row.descripcion),
  ];
  return checks.filter(Boolean).length;
}

function findNormalizedWindowIndexes(items, phrase, maxItems = 20) {
  const normalizedPhrase = normalizeForMatch(phrase);
  if (!normalizedPhrase) return [];

  for (let start = 0; start < items.length; start += 1) {
    let windowText = "";
    const indexes = [];

    for (let end = start; end < items.length && indexes.length < maxItems; end += 1) {
      const itemText = items[end].text;
      if (!itemText) continue;

      windowText = windowText ? `${windowText} ${itemText}` : itemText;
      indexes.push(items[end].index);

      if (windowText.includes(normalizedPhrase) || normalizedPhrase.includes(windowText)) {
        return indexes;
      }

      if (windowText.length > normalizedPhrase.length * 1.8 + 20) {
        break;
      }
    }
  }

  return [];
}

function findEvaluationRowPartIndexes(textRow, evaluationRow) {
  const indexes = new Set();
  findNormalizedWindowIndexes(textRow.items, evaluationRow.tipo, 8).forEach((index) =>
    indexes.add(index)
  );

  const expectedWeight = normalizeWeight(evaluationRow.ponderacion);
  if (expectedWeight !== null) {
    textRow.items
      .filter((item) => textHasWeight(item.text, expectedWeight))
      .forEach((item) => indexes.add(item.index));
  }

  findNormalizedWindowIndexes(textRow.items, evaluationRow.descripcion, 24).forEach((index) =>
    indexes.add(index)
  );

  return Array.from(indexes);
}

function groupTextItemsByLine(textItems, viewport) {
  const items = textItems
    .map((item, index) => {
      const rect = textItemToRect(item, viewport);
      return {
        index,
        rect,
        centerY: rect.top + rect.height / 2,
        text: normalizeForMatch(item.str),
      };
    })
    .filter((item) => item.text);

  const rows = [];
  for (const item of items.sort((a, b) => a.centerY - b.centerY)) {
    const row = rows.find((candidate) => Math.abs(candidate.centerY - item.centerY) <= 7);
    if (row) {
      row.items.push(item);
      row.centerY =
        row.items.reduce((sum, current) => sum + current.centerY, 0) / row.items.length;
    } else {
      rows.push({ centerY: item.centerY, items: [item] });
    }
  }

  return rows.map((row) => ({
    ...row,
    items: row.items.sort((a, b) => a.rect.left - b.rect.left),
    text: row.items.map((item) => item.text).join(" "),
  }));
}

function findEvaluationRowItemIndexes(textItems, viewport, evaluationRows) {
  if (!evaluationRows?.length) return [];

  const matchedIndexes = new Set();
  const textRows = groupTextItemsByLine(textItems, viewport);

  for (const evaluationRow of evaluationRows) {
    let bestMatch = null;
    for (const textRow of textRows) {
      const score = evaluationRowScore(textRow.text, evaluationRow);
      if (!score) continue;

      const expectedWeight = normalizeWeight(evaluationRow.ponderacion);
      const minimumScore = expectedWeight !== null ? 2 : 1;
      if (score < minimumScore) continue;
      if (!bestMatch || score > bestMatch.score) {
        bestMatch = { score, textRow };
      }
    }

    if (bestMatch?.textRow) {
      const partIndexes = findEvaluationRowPartIndexes(bestMatch.textRow, evaluationRow);
      const indexes = partIndexes.length
        ? partIndexes
        : bestMatch.textRow.items.map((item) => item.index);
      indexes.forEach((index) => matchedIndexes.add(index));
    }
  }

  return Array.from(matchedIndexes);
}

function shouldEvaluateHighlightOnPage(highlight, pageNumber) {
  const candidatePages = [
    highlight.page,
    ...(Array.isArray(highlight.pageNumbers) ? highlight.pageNumbers : []),
  ]
    .map((page) => Number(page))
    .filter((page) => Number.isFinite(page) && page > 0);

  if (!candidatePages.length) return true;
  return candidatePages.some((page) => Math.abs(page - pageNumber) <= 1);
}

async function loadTextSegment(pdfDocument, pageNumber, pageCount) {
  if (pageNumber < 1 || pageNumber > pageCount) return null;

  const page = await pdfDocument.getPage(pageNumber);
  const textContent = await page.getTextContent();
  return {
    pageNumber,
    textItems: textContent.items,
    viewport: null,
  };
}

function buildHighlightRects(
  textItems,
  viewport,
  highlights,
  activeHighlightId,
  pageNumber = null,
  pageSegments = null
) {
  const searchableSegments = pageSegments || [{ pageNumber, textItems, viewport }];

  return highlights.flatMap((highlight, highlightIndex) => {
    const evidenceRects = rectsFromEvidence(highlight).map((rect) => ({
      ...rect,
      isFocused: highlight.highlightId === activeHighlightId,
    }));
    if (evidenceRects.length) return evidenceRects;

    const structuredIndexes = highlight.evaluationRows?.length
      ? findEvaluationRowItemIndexes(textItems, viewport, highlight.evaluationRows)
      : [];
    const matchedRects = structuredIndexes.length
      ? structuredIndexes.map((itemIndex) => textItemToRect(textItems[itemIndex], viewport))
      : findMatchingTextRectsInSegments(
          searchableSegments,
          highlight.matchText || highlight.text,
          pageNumber
        );

    return matchedRects.map((rect, rectIndex) => ({
      ...rect,
      color: highlight.color,
      severity: highlight.severity,
      title: `NRC ${highlight.nrc}: ${highlight.variable}`,
      isFocused: highlight.highlightId === activeHighlightId,
      key: `${highlight.inconsistencyId}-${highlightIndex}-${rectIndex}`,
    }));
  });
}
// ═══════════════════════════════════════════════════════════════════════════════
// REPORT VIEW  (grouped by section)
// ═══════════════════════════════════════════════════════════════════════════════
function ReportView({ report, onEvidenceSelect }) {
  const counts = report.summary?.severity_counts || {};
  const outlier = report.summary?.possible_outlier;

  // Group inconsistencies by section
  const bySection = report.inconsistencies.reduce((acc, item) => {
    (acc[item.section] = acc[item.section] || []).push(item);
    return acc;
  }, {});
  const sections = Object.entries(bySection);

  return (
    <section className="report">
      <div className="report-header">
        <h2>Reporte comparativo</h2>
        <span className="time">{report.processing_time_seconds}s</span>
      </div>

      <div className="severity-summary">
        <span className="sev-chip sev-critica">
          Críticas: {counts.Crítica ?? counts.critica ?? 0}
        </span>
        <span className="sev-chip sev-moderada">
          Moderadas: {counts.Moderada ?? counts.moderada ?? 0}
        </span>
        <span className="sev-chip sev-menor">
          Menores: {counts.Menor ?? counts.menor ?? 0}
        </span>
      </div>

      {outlier?.nrc && (
        <div className="outlier">
          <AlertTriangle size={17} aria-hidden="true" />
          NRC {outlier.nrc} se aleja más del patrón del grupo (
          {outlier.alert_count ?? outlier.alerts ?? "?"} alertas).
        </div>
      )}

      {report.inconsistencies.length === 0 ? (
        <p className="message ok">
          No se detectaron inconsistencias principales para los apartados del MVP.
        </p>
      ) : (
        <div className="report-sections">
          {sections.map(([section, items]) => (
            <div key={section} className="report-section-group">
              <div className="report-section-heading">
                <div>
                  <h4 className="report-section-name">{formatSyllabusLabel(section)}</h4>
                </div>
                <span className="report-section-count">
                  {items.length} hallazgo{items.length !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="inconsistency-list">
                {items.map((item) => (
                  <InconsistencyCard
                    key={item.id}
                    item={item}
                    onEvidenceSelect={onEvidenceSelect}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function InconsistencyCard({ item, onEvidenceSelect }) {
  const evidence = normalizeEvidence(item.evidence);
  const [showEvidence, setShowEvidence] = useState(false);

  function handleEvidenceKeyDown(event, quote, index) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onEvidenceSelect?.(quote, item, index);
  }

  return (
    <div className="inconsistency-card">
      <div className="inconsistency-header">
        <SeverityBadge severity={item.severity} />
        <span className="inconsistency-variable">
          {formatSyllabusLabel(item.variable)}
        </span>
        <span className="inconsistency-nrcs">
          NRC: {item.involved_nrcs.join(", ")}
        </span>
      </div>
      <p className="inconsistency-diff">{item.difference}</p>
      {item.suggestion && (
        <p className="inconsistency-suggestion">{item.suggestion}</p>
      )}
      {evidence.length > 0 && (
        <>
          <button
            type="button"
            className="evidence-toggle"
            onClick={() => setShowEvidence((current) => !current)}
            aria-expanded={showEvidence}
          >
            <Quote size={15} aria-hidden="true" />
            {showEvidence ? "Ocultar citas" : `Ver citas (${evidence.length})`}
            <ChevronDown
              size={15}
              className={`evidence-toggle-icon ${showEvidence ? "is-open" : ""}`}
              aria-hidden="true"
            />
          </button>
          {showEvidence && (
            <div className="evidence-list" aria-label="Citas textuales usadas en el análisis">
              {evidence.map((quote, index) => (
                <blockquote
                  key={`${quote.nrc}-${index}`}
                  className={`evidence-item evidence-item-${quote.matchStatus}`}
                  role="button"
                  tabIndex={0}
                  title={quote.page ? "Ir a esta cita en el PDF" : "Buscar esta cita en el PDF"}
                  onClick={() => onEvidenceSelect?.(quote, item, index)}
                  onKeyDown={(event) => handleEvidenceKeyDown(event, quote, index)}
                >
                  <span className="evidence-meta">
                    <span className="evidence-nrc">NRC {quote.nrc}</span>
                    {evidenceStatusLabel(quote.matchStatus) && (
                      <span className={`evidence-status evidence-status-${quote.matchStatus}`}>
                        {evidenceStatusLabel(quote.matchStatus)}
                      </span>
                    )}
                  </span>
                  <p>{quote.text}</p>
                  {quote.page && <small>Página {quote.page}</small>}
                </blockquote>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SYLLABUS DOCUMENT SELECTOR
// ═══════════════════════════════════════════════════════════════════════════════
function SyllabusDocumentSelector({ syllabi, activeIndex, onSelect }) {
  if (!syllabi.length) {
    return (
      <section className="documents-overview">
        <div className="empty-pdf-state">
          <FileText size={30} aria-hidden="true" />
          <p>Este curso no tiene PDFs asociados.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="documents-overview" aria-label="Documentos del curso">
      <div className="viewer-header">
        <div>
          <h3>Documentos del curso</h3>
          <p>
            {syllabi.length} syllabus disponibles · {activeIndex + 1} de{" "}
            {syllabi.length}
          </p>
        </div>
      </div>

      <div className="syllabus-track" role="tablist" aria-label="Syllabus disponibles">
        {syllabi.map((s, index) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={index === activeIndex}
            className={`syllabus-tab ${index === activeIndex ? "is-active" : ""}`}
            onClick={() => onSelect(index)}
          >
            <strong>NRC {s.nrc}</strong>
            <span>{s.original_filename}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SYLLABUS PDF VIEWER
// ═══════════════════════════════════════════════════════════════════════════════
function PdfRenderedPage({
  pdfDocument,
  pageNumber,
  pageCount,
  highlights,
  activeHighlightId,
  isTargetPage,
  onPageReady,
  onFocusedMatch,
}) {
  const canvasRef = useRef(null);
  const [pageState, setPageState] = useState({
    loading: true,
    width: 0,
    height: 0,
    textItems: [],
    viewport: null,
    rects: [],
  });

  useEffect(() => {
    let cancelled = false;
    let renderTask = null;

    async function renderPage() {
      setPageState((current) => ({
        ...current,
        loading: true,
        textItems: [],
        viewport: null,
        rects: [],
      }));

      try {
        const page = await pdfDocument.getPage(pageNumber);
        if (cancelled) return;

        const viewport = page.getViewport({ scale: PDF_RENDER_SCALE });
        const canvas = canvasRef.current;
        const context = canvas?.getContext("2d");
        if (!canvas || !context) return;

        canvas.width = Math.ceil(viewport.width);
        canvas.height = Math.ceil(viewport.height);
        renderTask = page.render({ canvasContext: context, viewport });

        const [textContent] = await Promise.all([page.getTextContent(), renderTask.promise]);
        if (cancelled) return;

        setPageState({
          loading: false,
          width: viewport.width,
          height: viewport.height,
          textItems: textContent.items,
          viewport,
          rects: [],
        });
      } catch {
        if (!cancelled) {
          setPageState((current) => ({
            ...current,
            loading: false,
            textItems: [],
            viewport: null,
            rects: [],
          }));
        }
      }
    }

    renderPage();

    return () => {
      cancelled = true;
      renderTask?.cancel?.();
    };
  }, [pageNumber, pdfDocument]);

  useEffect(() => {
    if (pageState.loading || !pageState.viewport) return;

    let cancelled = false;

    async function updateHighlightRects() {
      const pageHighlights = highlights.filter((highlight) =>
        shouldEvaluateHighlightOnPage(highlight, pageNumber)
      );
      if (!pageHighlights.length) {
        setPageState((current) => ({ ...current, rects: [] }));
        onPageReady?.(pageNumber);
        return;
      }

      const needsBoundarySearch = pageHighlights.some(
        (highlight) => !highlight.rects?.length && !highlight.evaluationRows?.length
      );
      const [previousSegment, nextSegment] = needsBoundarySearch
        ? await Promise.all([
            loadTextSegment(pdfDocument, pageNumber - 1, pageCount).catch(() => null),
            loadTextSegment(pdfDocument, pageNumber + 1, pageCount).catch(() => null),
          ])
        : [null, null];
      if (cancelled) return;

      const pageSegments = [
        previousSegment,
        {
          pageNumber,
          textItems: pageState.textItems,
          viewport: pageState.viewport,
        },
        nextSegment,
      ].filter(Boolean);
      const rects = buildHighlightRects(
        pageState.textItems,
        pageState.viewport,
        pageHighlights,
        activeHighlightId,
        pageNumber,
        pageSegments
      );
      const focusedRect = rects.find((rect) => rect.isFocused);

      setPageState((current) => ({ ...current, rects }));
      if (focusedRect) {
        onFocusedMatch?.(pageNumber, focusedRect.top);
      } else {
        onPageReady?.(pageNumber);
      }
    }

    updateHighlightRects();

    return () => {
      cancelled = true;
    };
  }, [
    activeHighlightId,
    highlights,
    onFocusedMatch,
    onPageReady,
    pageCount,
    pdfDocument,
    pageNumber,
    pageState.loading,
    pageState.textItems,
    pageState.viewport,
  ]);

  return (
    <div
      data-page-number={pageNumber}
      className="pdf-page"
      style={{
        width: pageState.width || undefined,
        minHeight: pageState.height || undefined,
      }}
    >
      {pageState.loading && (
        <div className="pdf-page-loading">
          <Loader2 className="spin" size={18} />
        </div>
      )}
      <canvas ref={canvasRef} className="pdf-canvas" />
      <div className="pdf-highlight-layer" aria-hidden="true">
        {pageState.rects.map((rect) => (
          <span
            key={rect.key}
            className={`pdf-highlight pdf-highlight-${rect.severity}${
              rect.isFocused ? " is-focused" : ""
            }`}
            title={rect.title}
            style={{
              left: `${rect.left}px`,
              top: `${rect.top}px`,
              width: `${rect.width}px`,
              height: `${rect.height}px`,
              background: rect.color,
            }}
          />
        ))}
      </div>
      {isTargetPage && <span className="pdf-page-anchor" aria-hidden="true" />}
    </div>
  );
}

function PdfDocumentViewer({ syllabus, highlights = [], jumpTarget, onLayoutReady }) {
  const [pdfDocument, setPdfDocument] = useState(null);
  const [pageCount, setPageCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const documentRef = useRef(null);
  const lastScrolledTargetRef = useRef(null);
  const pdfUrl = syllabusViewUrl(syllabus.id);

  const targetPage = Number(jumpTarget?.page) || null;
  const activeHighlightId = jumpTarget?.highlightId || null;

  function scrollToPage(pageNumber, pageOffset = 0) {
    const container = documentRef.current;
    const pageElement = container?.querySelector(`[data-page-number="${pageNumber}"]`);
    if (!container || !pageElement) return;

    const centeredOffset = Math.max(pageOffset - container.clientHeight * 0.32, 0);
    container.scrollTo({
      top: Math.max(pageElement.offsetTop - container.offsetTop + centeredOffset - 12, 0),
      behavior: "smooth",
    });
  }

  function markTargetScrolled(pageNumber) {
    if (!jumpTarget?.requestedAt) return false;
    const scrollKey = `${jumpTarget.requestedAt}-${pageNumber}`;
    if (lastScrolledTargetRef.current === scrollKey) return false;
    lastScrolledTargetRef.current = scrollKey;
    return true;
  }

  function handlePageReady(pageNumber) {
    if (targetPage !== pageNumber || !markTargetScrolled(pageNumber)) return;
    scrollToPage(pageNumber);
  }

  function handleFocusedMatch(pageNumber, pageOffset) {
    if (!markTargetScrolled(pageNumber)) return;
    scrollToPage(pageNumber, pageOffset);
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPdfDocument(null);
    setPageCount(0);

    const loadingTask = pdfjsLib.getDocument({ url: pdfUrl });
    loadingTask.promise
      .then((loadedDocument) => {
        if (cancelled) {
          loadedDocument.destroy();
          return;
        }
        setPdfDocument(loadedDocument);
        setPageCount(loadedDocument.numPages);
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          setError("No se pudo renderizar el PDF en el visor.");
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
      loadingTask.destroy();
    };
  }, [pdfUrl]);

  useEffect(() => {
    if (loading || !jumpTarget?.requestedAt) return undefined;

    const frame = window.requestAnimationFrame(() => onLayoutReady?.());
    const timeout = window.setTimeout(() => onLayoutReady?.(), 220);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timeout);
    };
  }, [jumpTarget?.requestedAt, loading, onLayoutReady]);

  if (loading) {
    return (
      <div className="pdf-render-state">
        <Loader2 className="spin" size={22} />
        <p>Cargando PDF…</p>
      </div>
    );
  }

  if (error) {
    return <p className="message error">{error}</p>;
  }

  return (
    <div ref={documentRef} className="pdf-document">
      {Array.from({ length: pageCount }, (_, index) => (
        <PdfRenderedPage
          key={`${syllabus.id}-${index + 1}`}
          pdfDocument={pdfDocument}
          pageNumber={index + 1}
          pageCount={pageCount}
          highlights={highlights}
          activeHighlightId={activeHighlightId}
          isTargetPage={targetPage === index + 1}
          onPageReady={handlePageReady}
          onFocusedMatch={handleFocusedMatch}
        />
      ))}
    </div>
  );
}

function SyllabusPdfViewer({
  syllabi,
  activeIndex,
  onSelect,
  highlights = [],
  jumpTarget,
  viewerRef,
  onLayoutReady,
}) {
  const activeSyllabus = syllabi[activeIndex];

  if (!activeSyllabus) {
    return null;
  }

  const activeHighlights = highlights.filter(
    (highlight) => highlight.nrc === String(activeSyllabus.nrc)
  );

  function moveBy(delta) {
    onSelect((current) => {
      const next = current + delta;
      if (next < 0) return syllabi.length - 1;
      if (next >= syllabi.length) return 0;
      return next;
    });
  }

  return (
    <section
      ref={viewerRef}
      className="syllabus-viewer"
      aria-label="Visor de syllabus del curso"
    >
      <div className="pdf-carousel-shell">
        <button
          type="button"
          className="icon-button viewer-side-button"
          onClick={() => moveBy(-1)}
          aria-label="Ver syllabus anterior"
          title="Anterior"
        >
          <ChevronLeft size={20} />
        </button>

        <div className="pdf-panel">
          <div className="pdf-panel-meta">
            <div className="pdf-title">
              <FileText size={18} aria-hidden="true" />
              <span>
                <strong>NRC {activeSyllabus.nrc}</strong>
                <small>{activeSyllabus.original_filename}</small>
              </span>
            </div>
            <div className="pdf-links">
              <span>{formatFileSize(activeSyllabus.file_size)}</span>
              <a
                className="pdf-open-link"
                href={syllabusDownloadUrl(activeSyllabus.id)}
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink size={15} aria-hidden="true" />
                Abrir
              </a>
            </div>
          </div>
          <div className="pdf-highlight-legend" aria-label="Leyenda de resaltados">
            <span>
              <i className="legend-dot legend-dot-critica" />
              Crítica
            </span>
            <span>
              <i className="legend-dot legend-dot-moderada" />
              Moderada
            </span>
            <span>
              <i className="legend-dot legend-dot-menor" />
              Menor
            </span>
          </div>
          <PdfDocumentViewer
            key={activeSyllabus.id}
            syllabus={activeSyllabus}
            highlights={activeHighlights}
            jumpTarget={
              jumpTarget?.nrc === String(activeSyllabus.nrc) ? jumpTarget : null
            }
            onLayoutReady={onLayoutReady}
          />
        </div>

        <button
          type="button"
          className="icon-button viewer-side-button"
          onClick={() => moveBy(1)}
          aria-label="Ver syllabus siguiente"
          title="Siguiente"
        >
          <ChevronRight size={20} />
        </button>
      </div>
    </section>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// DETAIL VIEW
// ═══════════════════════════════════════════════════════════════════════════════
function analysisStatusLabel(status) {
  if (status === "completed") return "Analizado";
  if (status === "queued") return "En cola";
  if (status === "processing") return "Analizando";
  if (status === "failed") return "Error";
  return "Pendiente";
}

export default function Course({
  course,
  report,
  loading,
  retryingAnalysis,
  onBack,
  onAnalyze,
}) {
  const color = course ? courseColor(course.id) : PALETTE[0];
  const syllabi = course?.syllabi ?? [];
  const [activeSyllabusIndex, setActiveSyllabusIndex] = useState(0);
  const [quoteJumpTarget, setQuoteJumpTarget] = useState(null);
  const viewerRef = useRef(null);
  const reportHighlights = useMemo(() => collectReportHighlights(report), [report]);
  const analysisStatus = report?.status || course?.latest_report_status;
  const analysisIsActive = ["queued", "processing"].includes(analysisStatus);
  const analysisFailed = analysisStatus === "failed";
  const reportIsReady = report?.status === "completed";

  const centerPdfViewer = useCallback((behavior = "smooth") => {
    const viewerElement = viewerRef.current;
    const targetElement =
      viewerElement?.querySelector(".pdf-document") ||
      viewerElement?.querySelector(".pdf-render-state") ||
      viewerElement?.querySelector(".pdf-panel");
    if (!targetElement) return;

    const rect = targetElement.getBoundingClientRect();
    const viewportOffset = Math.max((window.innerHeight - rect.height) / 2, 16);
    window.scrollTo({
      top: Math.max(window.scrollY + rect.top - viewportOffset, 0),
      behavior,
    });
  }, []);

  useEffect(() => {
    setActiveSyllabusIndex(0);
    setQuoteJumpTarget(null);
  }, [course?.id]);

  useEffect(() => {
    if (syllabi.length > 0 && activeSyllabusIndex >= syllabi.length) {
      setActiveSyllabusIndex(syllabi.length - 1);
    }
  }, [activeSyllabusIndex, syllabi.length]);

  useEffect(() => {
    if (!quoteJumpTarget?.requestedAt) return undefined;

    const frame = window.requestAnimationFrame(() => centerPdfViewer());
    const timeouts = [90, 260, 520].map((delay) =>
      window.setTimeout(() => centerPdfViewer(), delay)
    );

    return () => {
      window.cancelAnimationFrame(frame);
      timeouts.forEach((timeout) => window.clearTimeout(timeout));
    };
  }, [activeSyllabusIndex, centerPdfViewer, quoteJumpTarget?.requestedAt]);

  function handleEvidenceSelect(quote, item, evidenceIndex) {
    const quoteNrc = String(quote.nrc);
    const nextIndex = syllabi.findIndex((syllabus) => String(syllabus.nrc) === quoteNrc);
    if (nextIndex === -1) return;

    const page =
      Number(quote.page) ||
      (Array.isArray(quote.pageNumbers) ? Number(quote.pageNumbers[0]) : null) ||
      null;
    setActiveSyllabusIndex(nextIndex);
    setQuoteJumpTarget({
      nrc: quoteNrc,
      page,
      highlightId: `${item.id}-${evidenceIndex}`,
      requestedAt: Date.now(),
    });
  }

  return (
    <div className="detail-view">
      {/* Sticky nav */}
      <nav className="detail-nav">
        <button className="back-button" onClick={onBack}>
          <ArrowLeft size={17} />
          Todos los cursos
        </button>
      </nav>

      {loading || !course ? (
        <div className="loading-state detail-loading-state">
          <Loader2 className="spin" size={30} />
          <p>Cargando curso…</p>
        </div>
      ) : (
        <>
          {/* Course header */}
          <div
            className="detail-header"
            style={{
              "--card-bg": color.bg,
              "--card-border": color.border,
              "--card-accent": color.accent,
            }}
          >
            <div className="detail-header-bar" />
            <div className="detail-header-content">
              <div className="detail-meta">
                <span>{course.academic_period}</span>
                <span>{course.career}</span>
              </div>
              <h1 className="detail-code">{course.course_name}</h1>
              <p className="detail-name">{course.course_code}</p>
            </div>
            <div className="detail-actions">
              <span className={`analysis-status analysis-status--${analysisStatus || "pending"}`}>
                {analysisIsActive && <Loader2 className="spin" size={16} />}
                {analysisStatusLabel(analysisStatus)}
              </span>
            </div>
          </div>

          {/* Body: report + syllabus viewer */}
          <div className="detail-body">
            <main className="detail-main">
              <SyllabusDocumentSelector
                syllabi={syllabi}
                activeIndex={activeSyllabusIndex}
                onSelect={setActiveSyllabusIndex}
              />

              <div className="detail-analysis">
                {analysisIsActive ? (
                  <div className="analyzing-state">
                    <Loader2 className="spin" size={26} />
                    <p>
                      {analysisStatus === "queued"
                        ? "El análisis está en cola…"
                        : "Analizando syllabus con IA…"}
                      <br />
                      <small>Esto puede tardar unos minutos.</small>
                    </p>
                  </div>
                ) : reportIsReady ? (
                  <ReportView report={report} onEvidenceSelect={handleEvidenceSelect} />
                ) : analysisFailed ? (
                  <div className="no-report-state">
                    <AlertTriangle size={32} aria-hidden="true" />
                    <p>{report?.summary?.message || "El análisis falló."}</p>
                    <button
                      type="button"
                      className="primary-button"
                      onClick={onAnalyze}
                      disabled={retryingAnalysis}
                    >
                      {retryingAnalysis ? (
                        <Loader2 className="spin" size={18} />
                      ) : (
                        <RefreshCcw size={18} />
                      )}
                      {retryingAnalysis ? "Encolando…" : "Reintentar análisis"}
                    </button>
                  </div>
                ) : (
                  <div className="no-report-state">
                    <FileText size={32} aria-hidden="true" />
                    <p>
                      El análisis se iniciará automáticamente cuando subas un ZIP con
                      syllabus para este curso.
                    </p>
                  </div>
                )}
              </div>

              <SyllabusPdfViewer
                syllabi={syllabi}
                activeIndex={activeSyllabusIndex}
                onSelect={setActiveSyllabusIndex}
                highlights={reportHighlights}
                jumpTarget={quoteJumpTarget}
                viewerRef={viewerRef}
                onLayoutReady={centerPdfViewer}
              />
            </main>
          </div>
        </>
      )}
    </div>
  );
}
