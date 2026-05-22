import {
  AlertTriangle,
  BookOpen,
  CircleCheck,
  FileArchive,
  FileText,
  Loader2,
  RefreshCcw,
  Upload,
  X,
} from "lucide-react";
import { useState } from "react";
import { uploadZip } from "../api";

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
function UploadZone({ onUploaded }) {
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState([]);
  const [errors, setErrors] = useState([]);

  function addFiles(selected) {
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name));
      return [...prev, ...selected.filter((f) => !names.has(f.name))];
    });
  }

  function removeFile(index) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!files.length) return;
    setUploading(true);
    setResults([]);
    setErrors([]);
    const newResults = [];
    const newErrors = [];
    for (const file of files) {
      try {
        const res = await uploadZip(file);
        newResults.push(res);
      } catch (exc) {
        newErrors.push(`${file.name}: ${exc.message}`);
      }
    }
    setResults(newResults);
    setErrors(newErrors);
    setFiles([]);
    setUploading(false);
    await onUploaded();
  }

  const allRejected = results.flatMap((r) => r.rejected_files || []);

  return (
    <div className="upload-zone">
      <div className="upload-zone-inner">
        <FileArchive size={26} className="upload-zone-icon" aria-hidden="true" />
        <div className="upload-zone-text">
          <p>Arrastra archivos ZIP aquí o</p>
          <label className="upload-link">
            selecciona archivos
            <input
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

      {(results.length > 0 || errors.length > 0) && (
        <div className="upload-feedback">
          {results.map((res, i) => (
            <p key={i} className="message ok">
              {res.message}
            </p>
          ))}
          {allRejected.map((item) => (
            <p key={`${item.filename}-${item.reason}`} className="message warn">
              <strong>{item.filename}</strong>: {item.reason}
            </p>
          ))}
          {errors.map((e, i) => (
            <p key={i} className="message error">
              {e}
            </p>
          ))}
        </div>
      )}
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

// ═══════════════════════════════════════════════════════════════════════════════
// HOME VIEW
// ═══════════════════════════════════════════════════════════════════════════════
export default function Homepage({ courses, loading, onOpenCourse, onRefresh }) {
  return (
    <div className="home-view">
      <header className="app-header">
        <div>
          <h1>Revisión de Syllabus</h1>
          <p className="header-sub">
            Detecta inconsistencias entre secciones de un mismo curso
          </p>
        </div>
        <button className="ghost-button" onClick={onRefresh} disabled={loading}>
          {loading ? <Loader2 className="spin" size={18} /> : <RefreshCcw size={18} />}
          Actualizar
        </button>
      </header>

      <UploadZone onUploaded={onRefresh} />

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
          <div className="loading-state">
            <Loader2 className="spin" size={28} />
            <p>Cargando cursos…</p>
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
    </div>
  );
}
