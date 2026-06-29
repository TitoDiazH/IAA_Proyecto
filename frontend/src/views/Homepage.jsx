import {
  AlertTriangle,
  BookOpen,
  CircleCheck,
  Download,
  FileArchive,
  FileText,
  Loader2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { downloadConditionsExport, uploadZip } from "../api";

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
    const dropped = Array.from(e.dataTransfer.files).filter(
      (f) => f.type === "application/zip" || f.name.endsWith(".zip")
    );
    if (dropped.length > 0) addFiles(dropped);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!files.length) return;
    setUploading(true);
    for (const file of files) {
      try {
        const res = await uploadZip(file);
        onToast?.("ok", res.message);
        (res.rejected_files || []).forEach((item) =>
          onToast?.("warn", `${item.filename}: ${item.reason}`)
        );
      } catch (exc) {
        onToast?.("error", `${file.name}: ${exc.message}`);
      }
    }
    setFiles([]);
    setUploading(false);
    await onUploaded();
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
          <p>Arrastra archivos ZIP aquí o</p>
          <label className="upload-link">
            selecciona archivos
            <input
              ref={inputRef}
              type="file"
              accept=".zip,application/zip"
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
              <FileArchive size={14} aria-hidden="true" />
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
function CourseCard({ course, onClick }) {
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

  return (
    <button
      className={`course-card ${isProcessing ? "course-card--processing" : ""}`}
      style={{
        "--card-bg": color.bg,
        "--card-border": color.border,
        "--card-accent": color.accent,
      }}
      onClick={onClick}
      disabled={isProcessing}
      aria-label={
        isProcessing
          ? `${course.course_name} está siendo analizado`
          : `Abrir curso ${course.course_name}`
      }
      title={isProcessing ? "Disponible cuando finalice el análisis" : undefined}
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
  );
}

function ConditionsExportPreview({ table }) {
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
      const blob = await downloadConditionsExport({ format, filename });
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
  exportTable,
  loading,
  onOpenCourse,
  onRefresh,
  addToast,
}) {
  return (
    <div className="home-view">
      <UploadZone onUploaded={onRefresh} onToast={addToast} />

      <div className="courses-section">
        <div className="courses-section-header">
          <h2>
            <BookOpen size={18} aria-hidden="true" />
            Cursos
          </h2>
          {courses.length > 0 && (
            <span className="courses-count">{courses.length} cursos</span>
          )}
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
            <h3>No hay cursos cargados</h3>
            <p>Sube un archivo ZIP con syllabus en PDF para comenzar.</p>
          </div>
        ) : (
          <div className="course-grid">
            {courses.map((course) => (
              <CourseCard
                key={course.id}
                course={course}
                onClick={() => onOpenCourse(course.id)}
              />
            ))}
          </div>
        )}
      </div>

      <ConditionsExportPreview table={exportTable} />
    </div>
  );
}
