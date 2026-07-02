import {
  AlertTriangle,
  BookOpen,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  Download,
  FileArchive,
  FileText,
  Loader2,
  MoreVertical,
  RefreshCcw,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { downloadConditionsExport, getModelPreference, setModelPreference, uploadPdfs, uploadZip } from "../api";
import { formatPeriod, shiftPeriod } from "../periods";

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

function isZipFile(file) {
  return file.type === "application/zip" || file.name.toLowerCase().endsWith(".zip");
}

function isPdfFile(file) {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

// ═══════════════════════════════════════════════════════════════════════════════
// UPLOAD ZONE  (supports multiple files)
// ═══════════════════════════════════════════════════════════════════════════════
function UploadZone({ onUploaded, onToast }) {
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const dragCounter = useRef(0);
  const inputRef = useRef(null);

  function addFiles(selected) {
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name));
      return [...prev, ...selected.filter((f) => !names.has(f.name))];
    });
  }

  function removeFile(index) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  function handleDragEnter(e) {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current += 1;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setDragActive(true);
    }
  }

  function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current -= 1;
    if (dragCounter.current === 0) {
      setDragActive(false);
    }
  }

  function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
  }

  function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    dragCounter.current = 0;
    const dropped = Array.from(e.dataTransfer.files).filter((f) => isZipFile(f) || isPdfFile(f));
    if (dropped.length > 0) addFiles(dropped);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!files.length) return;
    setUploading(true);

    const zipFiles = files.filter(isZipFile);
    const pdfFiles = files.filter(isPdfFile);

    for (const file of zipFiles) {
      try {
        const res = await uploadZip(file);
        onToast?.("ok", res.message);
        (res.rejected_files || []).forEach((item) =>
          onToast?.("warn", `${item.filename}: ${item.reason}`)
        );
        // refresh immediately after each file so new cards appear right away
        onUploaded?.(res);
      } catch (exc) {
        onToast?.("error", `${file.name}: ${exc.message}`);
      }
    }

    if (pdfFiles.length > 0) {
      try {
        const res = await uploadPdfs(pdfFiles);
        onToast?.("ok", res.message);
        (res.rejected_files || []).forEach((item) =>
          onToast?.("warn", `${item.filename}: ${item.reason}`)
        );
        onUploaded?.(res);
      } catch (exc) {
        onToast?.("error", exc.message);
      }
    }

    setFiles([]);
    setUploading(false);
  }

  function handleZoneClick(e) {
    if (e.target.closest("label, button, input, a")) return;
    inputRef.current?.click();
  }

  return (
    <div
      className={`upload-zone${dragActive ? " upload-zone--drag-active" : ""}`}
      onClick={handleZoneClick}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      <div className="upload-zone-inner">
        <FileArchive size={26} className="upload-zone-icon" aria-hidden="true" />
        <div className="upload-zone-text">
          <p>Arrastra archivos ZIP o PDF aquí o</p>
          <label className="upload-link">
            selecciona archivos
            <input
              ref={inputRef}
              type="file"
              accept=".zip,application/zip,.pdf,application/pdf"
              multiple
              onChange={(e) => {
                addFiles(Array.from(e.target.files || []));
                e.target.value = "";
              }}
            />
          </label>
        </div>
      </div>

      {files.length > 0 && (
        <ul className="file-queue">
          {files.map((f, i) => (
            <li key={f.name}>
              {isPdfFile(f) ? (
                <FileText size={14} aria-hidden="true" />
              ) : (
                <FileArchive size={14} aria-hidden="true" />
              )}
              <span>{f.name}</span>
              <button
                type="button"
                className="remove-file"
                onClick={() => removeFile(i)}
                aria-label={`Quitar ${f.name}`}
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {files.length > 0 && (
        <form onSubmit={handleSubmit}>
          <button className="primary-button upload-submit" disabled={uploading}>
            {uploading ? <Loader2 className="spin" size={18} /> : <Upload size={18} />}
            {uploading
              ? "Procesando…"
              : `Subir ${files.length} archivo${files.length !== 1 ? "s" : ""}`}
          </button>
        </form>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// PERIOD SELECTOR
// ═══════════════════════════════════════════════════════════════════════════════
function PeriodSelector({ period, onChange }) {
  return (
    <div className="period-selector" role="group" aria-label="Periodo académico">
      <button
        type="button"
        className="icon-button period-nav-btn"
        onClick={() => onChange(shiftPeriod(period, -1))}
        aria-label="Periodo anterior"
        title="Periodo anterior"
      >
        <ChevronLeft size={18} aria-hidden="true" />
      </button>
      <span className="period-label" aria-live="polite">
        {formatPeriod(period)}
      </span>
      <button
        type="button"
        className="icon-button period-nav-btn"
        onClick={() => onChange(shiftPeriod(period, 1))}
        aria-label="Periodo siguiente"
        title="Periodo siguiente"
      >
        <ChevronRight size={18} aria-hidden="true" />
      </button>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MODEL SELECTOR TAG
// ═══════════════════════════════════════════════════════════════════════════════
function ModelSelectorTag({ onToast }) {
  const [available, setAvailable] = useState([]);
  const [selected, setSelected] = useState(null);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const containerRef = useRef(null);

  useEffect(() => {
    getModelPreference()
      .then((data) => {
        setAvailable(data.available || []);
        setSelected(data.selected);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  async function handleSelect(modelId) {
    setOpen(false);
    if (modelId === selected) return;
    const previous = selected;
    setSelected(modelId);
    setSaving(true);
    try {
      await setModelPreference(modelId);
    } catch (exc) {
      setSelected(previous);
      onToast?.("error", exc.message || "No se pudo cambiar el modelo de IA");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="model-selector">
        <button type="button" className="model-selector-tag" disabled aria-busy="true">
          <Sparkles size={14} aria-hidden="true" />
          <span className="sk model-selector-skeleton" aria-hidden="true" />
        </button>
      </div>
    );
  }

  if (available.length === 0) return null;

  const selectedModel = available.find((model) => model.id === selected);

  return (
    <div className="model-selector" ref={containerRef}>
      <button
        type="button"
        className="model-selector-tag"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="listbox"
        disabled={saving}
        title="Cambiar el modelo de IA usado para analizar los syllabus"
      >
        <Sparkles size={14} aria-hidden="true" />
        {selectedModel?.label || "Modelo de IA"}
        <ChevronDown size={14} className={`model-selector-chevron${open ? " is-open" : ""}`} aria-hidden="true" />
      </button>

      {open && (
        <div className="model-selector-dropdown" role="listbox">
          {available.map((model) => (
            <button
              type="button"
              key={model.id}
              role="option"
              aria-selected={model.id === selected}
              className={`model-option${model.id === selected ? " model-option--selected" : ""}`}
              onClick={() => handleSelect(model.id)}
            >
              <span className="model-option-label">
                {model.id === selected && <Check size={14} aria-hidden="true" />}
                {model.label}
              </span>
              <span className="model-option-description">{model.description}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SKELETON CARD
// ═══════════════════════════════════════════════════════════════════════════════
function SkeletonCard() {
  return (
    <div className="course-card skeleton-card" aria-hidden="true">
      <div className="card-top-bar sk sk-bar" />
      <div className="card-body">
        <div className="sk sk-line sk-title" />
        <div className="sk sk-line sk-subtitle" />
        <div className="card-meta">
          <div className="sk sk-chip" />
          <div className="sk sk-chip" />
        </div>
      </div>
      <div className="card-footer">
        <div className="sk sk-chip" />
        <div className="sk sk-chip" />
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// COURSE CARD
// ═══════════════════════════════════════════════════════════════════════════════
function CourseCard({ course, onClick, onDelete, onAnalyze, selecting, selected, onToggleSelect }) {
  const color = courseColor(course.id);
  const status = course.latest_report_status;
  const isProcessing = ["queued", "processing"].includes(status);
  const inconsistencyCount = course.latest_report_inconsistency_count ?? 0;
  const hasInconsistencies = status === "completed" && inconsistencyCount > 0;
  const isClean = status === "completed" && inconsistencyCount === 0;
  const statusLabel =
    hasInconsistencies
      ? `${inconsistencyCount} hallazgo${inconsistencyCount !== 1 ? "s" : ""}`
      : isClean
        ? "Sin hallazgos"
      : status === "queued"
        ? "En cola"
        : status === "processing"
          ? "Analizando"
          : status === "failed"
            ? "Error"
            : "Pendiente";

  const [menuOpen, setMenuOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!menuOpen) return;
    function handleClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false);
        setConfirming(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen]);

  function handleCardClick() {
    if (selecting) { onToggleSelect(course.id); return; }
    onClick();
  }

  return (
    <div className={`course-card-wrap${selected ? " course-card-wrap--selected" : ""}`}>
      <button
        className={`course-card ${isProcessing && !selecting ? "course-card--processing" : ""}`}
        style={{
          "--card-bg": color.bg,
          "--card-border": color.border,
          "--card-accent": color.accent,
        }}
        onClick={handleCardClick}
        disabled={isProcessing && !selecting}
        aria-pressed={selecting ? selected : undefined}
        aria-label={
          selecting
            ? `${selected ? "Deseleccionar" : "Seleccionar"} ${course.course_name}`
            : isProcessing
              ? `${course.course_name} está siendo analizado`
              : `Abrir curso ${course.course_name}`
        }
        title={isProcessing && !selecting ? "Disponible cuando finalice el análisis" : undefined}
      >
        <div className="card-top-bar" />
        <div className="card-body">
          <div className="card-title">{course.course_name}</div>
          <div className="card-subtitle">{course.course_code}</div>
          <div className="card-meta">
            <span className="card-chip">{course.academic_period}</span>
            <span className="card-chip">{course.career}</span>
          </div>
        </div>
        <div className="card-footer">
          <span className="card-count">
            <FileText size={13} aria-hidden="true" />
            {course.syllabus_count} syllabus
          </span>
          <span
            className={`card-status ${isClean ? "card-status--done" : ""} ${
              hasInconsistencies ? "card-status--warning" : ""
            } ${status === "failed" ? "card-status--error" : ""} ${
              isProcessing ? "card-status--active" : ""
            }`}
          >
            {isProcessing && <Loader2 className="spin" size={14} aria-hidden="true" />}
            {hasInconsistencies && <AlertTriangle size={14} aria-hidden="true" />}
            {isClean && <CircleCheck size={14} aria-hidden="true" />}
            {status === "failed" && <AlertTriangle size={14} aria-hidden="true" />}
            {statusLabel}
          </span>
        </div>
      </button>

      {selecting ? (
        <div className="card-select-indicator" aria-hidden="true">
          <div className={`card-checkbox${selected ? " card-checkbox--checked" : ""}`}>
            {selected && <Check size={11} strokeWidth={3} />}
          </div>
        </div>
      ) : (
        <div className="card-menu" ref={menuRef}>
          <button
            type="button"
            className="card-menu-trigger"
            aria-label="Opciones del curso"
            aria-expanded={menuOpen}
            onClick={(e) => {
              e.stopPropagation();
              setMenuOpen((o) => !o);
              setConfirming(false);
            }}
          >
            <MoreVertical size={20} strokeWidth={2.5} aria-hidden="true" />
          </button>

          {menuOpen && (
            <div className="card-menu-dropdown" role="menu">
              {!confirming ? (
                <>
                  <button
                    type="button"
                    className="card-menu-item"
                    role="menuitem"
                    disabled={isProcessing}
                    title={isProcessing ? "Ya hay un análisis en curso" : undefined}
                    onClick={() => { setMenuOpen(false); onAnalyze(course.id); }}
                  >
                    <RefreshCcw size={14} aria-hidden="true" />
                    Reanalizar
                  </button>
                  <button
                    type="button"
                    className="card-menu-item card-menu-item--danger"
                    role="menuitem"
                    onClick={() => setConfirming(true)}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                    Eliminar curso
                  </button>
                </>
              ) : (
                <div className="card-menu-confirm">
                  <p>¿Eliminar este curso? Esta acción no se puede deshacer.</p>
                  <div className="card-menu-confirm-actions">
                    <button
                      type="button"
                      className="card-menu-item"
                      onClick={() => { setConfirming(false); setMenuOpen(false); }}
                    >
                      Cancelar
                    </button>
                    <button
                      type="button"
                      className="card-menu-item card-menu-item--danger"
                      onClick={() => { setMenuOpen(false); setConfirming(false); onDelete(course.id); }}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                      Eliminar
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ConditionsExportPreview({ table, academicPeriod }) {
  const [filename, setFilename] = useState("condiciones-aprobacion");
  const [format, setFormat] = useState("xlsx");
  const [modalOpen, setModalOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);
  const filenameInputRef = useRef(null);
  const headerRows = table?.header_rows || [];
  const rows = table?.rows || [];

  useEffect(() => {
    if (!modalOpen) return undefined;

    const timeout = window.setTimeout(() => filenameInputRef.current?.focus(), 0);
    function handleKeyDown(event) {
      if (event.key === "Escape" && !exporting) {
        setModalOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.clearTimeout(timeout);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [exporting, modalOpen]);

  async function handleExport() {
    setExporting(true);
    setError(null);
    try {
      const blob = await downloadConditionsExport({ format, filename, academicPeriod });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${filename || "condiciones-aprobacion"}.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setModalOpen(false);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setExporting(false);
    }
  }

  return (
    <section className="export-section" aria-label="Tabla exportable de condiciones">
      <div className="export-section-header">
        <div>
          <h2>Tabla de condiciones</h2>
          <p>
            {rows.length} fila{rows.length !== 1 ? "s" : ""} listas para exportar
          </p>
        </div>
        <button
          className="primary-button"
          type="button"
          onClick={() => {
            setError(null);
            setModalOpen(true);
          }}
          disabled={rows.length === 0}
        >
          <Download size={18} />
          Exportar
        </button>
      </div>

      {rows.length === 0 ? (
        <div className="export-empty-state">
          <FileText size={28} aria-hidden="true" />
          <p>La tabla aparecerá cuando finalice al menos un análisis.</p>
        </div>
      ) : (
        <div className="export-table-wrap">
          <table className="export-table">
            <thead>
              {headerRows.map((headerRow, rowIndex) => (
                <tr key={`header-${rowIndex}`}>
                  {headerRow.map((cell, cellIndex) => (
                    <th key={`${rowIndex}-${cellIndex}`}>{cell}</th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={`row-${rowIndex}`}>
                  {row.map((cell, cellIndex) => (
                    <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modalOpen && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !exporting) {
              setModalOpen(false);
            }
          }}
        >
          <div
            className="export-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="export-modal-title"
          >
            <div className="export-modal-header">
              <div>
                <h3 id="export-modal-title">Exportar tabla</h3>
                <p>
                  {rows.length} fila{rows.length !== 1 ? "s" : ""} disponibles
                </p>
              </div>
              <button
                type="button"
                className="icon-button modal-close-button"
                onClick={() => setModalOpen(false)}
                disabled={exporting}
                aria-label="Cerrar"
                title="Cerrar"
              >
                <X size={18} />
              </button>
            </div>

            <div className="export-modal-body">
              <label className="export-field">
                <span>Nombre</span>
                <input
                  ref={filenameInputRef}
                  className="export-name-input"
                  type="text"
                  value={filename}
                  onChange={(event) => setFilename(event.target.value)}
                />
              </label>

              <label className="export-field">
                <span>Formato</span>
                <select
                  className="export-format-select"
                  value={format}
                  onChange={(event) => setFormat(event.target.value)}
                >
                  <option value="xlsx">XLSX</option>
                  <option value="csv">CSV</option>
                </select>
              </label>

              {error && <p className="message error">{error}</p>}
            </div>

            <div className="export-modal-actions">
              <button
                className="ghost-button"
                type="button"
                onClick={() => setModalOpen(false)}
                disabled={exporting}
              >
                Cancelar
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={handleExport}
                disabled={exporting}
              >
                {exporting ? (
                  <Loader2 className="spin" size={18} />
                ) : (
                  <Download size={18} />
                )}
                {exporting ? "Exportando…" : "Confirmar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// HOME VIEW
// ═══════════════════════════════════════════════════════════════════════════════
export default function Homepage({
  courses,
  hasAnyCourses,
  exportTable,
  loading,
  selectedPeriod,
  onPeriodChange,
  onOpenCourse,
  onRefresh,
  onDeleteCourse,
  onDeleteMany,
  onAnalyzeCourse,
  addToast,
}) {
  const [selecting, setSelecting] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useEffect(() => {
    setSelecting(false);
    setSelectedIds(new Set());
    setConfirmingDelete(false);
  }, [selectedPeriod]);

  function toggleSelect(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function cancelSelect() {
    setSelecting(false);
    setSelectedIds(new Set());
    setConfirmingDelete(false);
  }

  function confirmDeleteSelected() {
    onDeleteMany([...selectedIds]);
    cancelSelect();
  }

  return (
    <div className="home-view">
      <UploadZone onUploaded={onRefresh} onToast={addToast} />

      <div className="top-controls-row">
        <PeriodSelector period={selectedPeriod} onChange={onPeriodChange} />
        <ModelSelectorTag onToast={addToast} />
      </div>

      <div className="courses-section">
        <div className="courses-section-header">
          <h2>
            <BookOpen size={18} aria-hidden="true" />
            Cursos
          </h2>
          <div className="courses-header-actions">
            {!selecting && courses.length > 0 && (
              <span className="courses-count">{courses.length} cursos</span>
            )}
            {courses.length > 0 && !selecting && (
              <button
                type="button"
                className="select-toggle-btn"
                onClick={() => setSelecting(true)}
              >
                Seleccionar
              </button>
            )}
            {selecting && (
              <>
                <button type="button" className="select-toggle-btn" onClick={cancelSelect}>
                  Cancelar
                </button>
                {selectedIds.size > 0 && (
                  <button
                    type="button"
                    className="select-delete-btn"
                    onClick={() => setConfirmingDelete(true)}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                    Eliminar {selectedIds.size}
                  </button>
                )}
              </>
            )}
          </div>
        </div>

        {loading && courses.length === 0 ? (
          <div className="course-grid" aria-busy="true" aria-label="Cargando cursos">
            {Array.from({ length: 8 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        ) : courses.length === 0 ? (
          <div className="empty-state">
            <FileArchive size={36} aria-hidden="true" />
            <h3>{hasAnyCourses ? "No hay cursos en este periodo" : "No hay cursos cargados"}</h3>
            <p>
              {hasAnyCourses
                ? "Cambia de periodo o sube un archivo ZIP o PDF para este periodo."
                : "Sube un archivo ZIP o PDF con syllabus para comenzar."}
            </p>
          </div>
        ) : (
          <div className="course-grid">
            {courses.map((course) => (
              <CourseCard
                key={course.id}
                course={course}
                onClick={() => onOpenCourse(course.id)}
                onDelete={onDeleteCourse}
                onAnalyze={onAnalyzeCourse}
                selecting={selecting}
                selected={selectedIds.has(course.id)}
                onToggleSelect={toggleSelect}
              />
            ))}
          </div>
        )}
      </div>

      <ConditionsExportPreview table={exportTable} academicPeriod={selectedPeriod} />

      {confirmingDelete && (
        <div className="modal-overlay" onClick={() => setConfirmingDelete(false)}>
          <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <div className="modal-icon">
              <Trash2 size={22} aria-hidden="true" />
            </div>
            <h3 className="modal-title">
              ¿Eliminar {selectedIds.size} curso{selectedIds.size !== 1 ? "s" : ""}?
            </h3>
            <p className="modal-body">
              Esta acción no se puede deshacer. Los syllabus y análisis asociados
              también serán eliminados permanentemente.
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="select-toggle-btn"
                onClick={() => setConfirmingDelete(false)}
              >
                Cancelar
              </button>
              <button
                type="button"
                className="select-delete-btn"
                onClick={confirmDeleteSelected}
              >
                <Trash2 size={14} aria-hidden="true" />
                Eliminar {selectedIds.size}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
