import {
  AlertTriangle,
  ArrowLeft,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  Loader2,
  PlayCircle,
  Quote,
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
  moderada: "rgba(245, 158, 11, 0.32)",
  menor: "rgba(37, 99, 235, 0.24)",
};

const SYLLABUS_LABELS = {
  evaluaciones: "Evaluaciones y Ponderaciones",
  evaluaciones_y_ponderaciones: "Evaluaciones y Ponderaciones",
  requisitos_aprobacion: "Requisitos de Aprobación",
  criterios_eximicion: "Criterios de Eximición",
  nota_final: "Nota Final",
  threshold: "Criterio de Eximición",
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

function parseEvaluationEvidenceText(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed.startsWith("[") && !trimmed.startsWith("{")) return null;

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

function findMatchingItemIndexes(textItems, quoteText) {
  const quote = normalizeForMatch(quoteText);
  if (quote.length < 4) return [];

  const itemTexts = textItems.map((item) => normalizeForMatch(item.str));
  for (let start = 0; start < itemTexts.length; start += 1) {
    let windowText = "";
    const indexes = [];

    for (let end = start; end < itemTexts.length && indexes.length < 80; end += 1) {
      const itemText = itemTexts[end];
      if (!itemText) continue;

      windowText = windowText ? `${windowText} ${itemText}` : itemText;
      indexes.push(end);

      const enoughContext = windowText.length >= Math.max(quote.length * 0.65, 12);
      if (windowText.includes(quote) || (enoughContext && quote.includes(windowText))) {
        return indexes;
      }

      if (windowText.length > quote.length * 1.8 + 40) {
        break;
      }
    }
  }

  return [];
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

    bestMatch?.textRow.items.forEach((item) => matchedIndexes.add(item.index));
  }

  return Array.from(matchedIndexes);
}

function buildHighlightRects(textItems, viewport, highlights, activeHighlightId) {
  return highlights.flatMap((highlight, highlightIndex) => {
    const structuredIndexes = highlight.evaluationRows?.length
      ? findEvaluationRowItemIndexes(textItems, viewport, highlight.evaluationRows)
      : [];
    const matchedIndexes = structuredIndexes.length
      ? structuredIndexes
      : findMatchingItemIndexes(textItems, highlight.text);
    return matchedIndexes.map((itemIndex) => ({
      ...textItemToRect(textItems[itemIndex], viewport),
      color: highlight.color,
      severity: highlight.severity,
      title: `NRC ${highlight.nrc}: ${highlight.variable}`,
      isFocused: highlight.highlightId === activeHighlightId,
      key: `${highlight.inconsistencyId}-${highlightIndex}-${itemIndex}`,
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
                  <span className="report-section-kicker">Apartado del syllabus</span>
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
                  className="evidence-item"
                  role="button"
                  tabIndex={0}
                  title="Ir a esta cita en el PDF"
                  onClick={() => onEvidenceSelect?.(quote, item, index)}
                  onKeyDown={(event) => handleEvidenceKeyDown(event, quote, index)}
                >
                  <span className="evidence-nrc">NRC {quote.nrc}</span>
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
    rects: [],
  });

  useEffect(() => {
    let cancelled = false;
    let renderTask = null;

    async function renderPage() {
      setPageState((current) => ({ ...current, loading: true, rects: [] }));

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

        const pageHighlights = highlights.filter(
          (highlight) => !highlight.page || Number(highlight.page) === pageNumber
        );
        const rects = buildHighlightRects(
          textContent.items,
          viewport,
          pageHighlights,
          activeHighlightId
        );
        const focusedRect = rects.find((rect) => rect.isFocused);
        setPageState({
          loading: false,
          width: viewport.width,
          height: viewport.height,
          rects,
        });
        if (focusedRect) {
          onFocusedMatch?.(pageNumber, focusedRect.top);
        } else {
          onPageReady?.(pageNumber);
        }
      } catch {
        if (!cancelled) {
          setPageState((current) => ({ ...current, loading: false, rects: [] }));
        }
      }
    }

    renderPage();

    return () => {
      cancelled = true;
      renderTask?.cancel?.();
    };
  }, [activeHighlightId, highlights, onFocusedMatch, onPageReady, pageNumber, pdfDocument]);

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
export default function Course({ course, report, analyzing, loading, onBack, onAnalyze }) {
  const color = course ? courseColor(course.id) : PALETTE[0];
  const syllabi = course?.syllabi ?? [];
  const [activeSyllabusIndex, setActiveSyllabusIndex] = useState(0);
  const [quoteJumpTarget, setQuoteJumpTarget] = useState(null);
  const viewerRef = useRef(null);
  const reportHighlights = useMemo(() => collectReportHighlights(report), [report]);

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

    const page = Number(quote.page) || null;
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
              <button
                className="primary-button"
                onClick={onAnalyze}
                disabled={analyzing}
              >
                {analyzing ? (
                  <Loader2 className="spin" size={18} />
                ) : (
                  <PlayCircle size={18} />
                )}
                {analyzing ? "Analizando…" : "Analizar"}
              </button>
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
                {analyzing ? (
                  <div className="analyzing-state">
                    <Loader2 className="spin" size={26} />
                    <p>
                      Analizando syllabus con IA local…
                      <br />
                      <small>Esto puede tardar unos minutos.</small>
                    </p>
                  </div>
                ) : report ? (
                  <ReportView report={report} onEvidenceSelect={handleEvidenceSelect} />
                ) : (
                  <div className="no-report-state">
                    <PlayCircle size={32} aria-hidden="true" />
                    <p>
                      Presiona <strong>Analizar</strong> para comparar los syllabus de este
                      curso.
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
