import {
  AlertTriangle,
  ChevronRight,
  FileArchive,
  FileText,
  Loader2,
  PlayCircle,
  RefreshCcw,
  Upload,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  analyzeCourse,
  getCourse,
  getLatestReport,
  listCourses,
  syllabusDownloadUrl,
  uploadZip,
} from "./api";

function groupByPeriod(courses) {
  return courses.reduce((acc, course) => {
    acc[course.academic_period] = acc[course.academic_period] || [];
    acc[course.academic_period].push(course);
    return acc;
  }, {});
}

function SeverityBadge({ severity }) {
  const className = `severity severity-${severity?.toLowerCase() || "none"}`;
  return <span className={className}>{severity || "Sin nivel"}</span>;
}

function EmptyState() {
  return (
    <section className="empty-state">
      <FileArchive size={36} aria-hidden="true" />
      <h2>No hay syllabus cargados</h2>
      <p>Sube un ZIP con archivos PDF para crear grupos por periodo y código de curso.</p>
    </section>
  );
}

function UploadPanel({ onUploaded }) {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!file) return;

    setUploading(true);
    setError(null);
    try {
      const response = await uploadZip(file);
      setResult(response);
      await onUploaded(response.course_ids?.[0]);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <section className="upload-panel" aria-label="Carga de ZIP">
      <form onSubmit={handleSubmit} className="upload-form">
        <label className="file-input">
          <Upload size={18} aria-hidden="true" />
          <span>{file ? file.name : "Seleccionar ZIP"}</span>
          <input
            type="file"
            accept=".zip,application/zip"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
          />
        </label>
        <button type="submit" className="primary-button" disabled={!file || uploading}>
          {uploading ? <Loader2 className="spin" size={18} /> : <Upload size={18} />}
          Subir ZIP
        </button>
      </form>

      {error && <p className="message error">{error}</p>}
      {result && (
        <div className="upload-result">
          <span>{result.message}</span>
          <span>{result.rejected_count} rechazados</span>
        </div>
      )}
      {result?.rejected_files?.length > 0 && (
        <ul className="rejected-list">
          {result.rejected_files.map((item) => (
            <li key={`${item.filename}-${item.reason}`}>
              <strong>{item.filename}</strong>: {item.reason}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CourseTable({ courses, selectedCourseId, onSelect }) {
  const grouped = useMemo(() => groupByPeriod(courses), [courses]);
  const periods = Object.keys(grouped).sort().reverse();

  if (!courses.length) return <EmptyState />;

  return (
    <section className="course-list" aria-label="Cursos agrupados">
      {periods.map((period) => (
        <div key={period} className="period-group">
          <div className="period-heading">
            <h2>{period}</h2>
            <span>{grouped[period].length} cursos</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Código</th>
                  <th>Curso</th>
                  <th>Carrera</th>
                  <th>Syllabus</th>
                  <th>Reporte</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {grouped[period].map((course) => (
                  <tr
                    key={course.id}
                    className={selectedCourseId === course.id ? "selected-row" : ""}
                    onClick={() => onSelect(course.id)}
                  >
                    <td className="mono">{course.course_code}</td>
                    <td>{course.course_name}</td>
                    <td>{course.career}</td>
                    <td>{course.syllabus_count}</td>
                    <td>{course.latest_report_id ? "Generado" : "Pendiente"}</td>
                    <td className="row-action">
                      <ChevronRight size={18} aria-hidden="true" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  );
}

function CourseDetail({ course, report, analyzing, onAnalyze, onLoadReport }) {
  if (!course) {
    return (
      <aside className="detail-panel">
        <div className="placeholder">Selecciona un curso para revisar sus syllabus.</div>
      </aside>
    );
  }

  return (
    <aside className="detail-panel">
      <div className="detail-header">
        <div>
          <p className="eyebrow">{course.academic_period} · {course.career}</p>
          <h2>{course.course_code}</h2>
          <p>{course.course_name}</p>
        </div>
        <button className="primary-button" onClick={onAnalyze} disabled={analyzing}>
          {analyzing ? <Loader2 className="spin" size={18} /> : <PlayCircle size={18} />}
          Analizar
        </button>
      </div>

      <section className="detail-section">
        <div className="section-title">
          <h3>Syllabus asociados</h3>
          {course.latest_report_id && (
            <button className="ghost-button" onClick={onLoadReport}>
              <RefreshCcw size={16} />
              Ver último reporte
            </button>
          )}
        </div>
        <div className="syllabus-list">
          {course.syllabi.map((syllabus) => (
            <a
              key={syllabus.id}
              className="syllabus-item"
              href={syllabusDownloadUrl(syllabus.id)}
              target="_blank"
              rel="noreferrer"
            >
              <FileText size={18} aria-hidden="true" />
              <span>
                <strong>NRC {syllabus.nrc}</strong>
                <small>{syllabus.original_filename}</small>
              </span>
              <em>{syllabus.extraction_status}</em>
            </a>
          ))}
        </div>
      </section>

      {report && <ReportView report={report} />}
    </aside>
  );
}

function ReportView({ report }) {
  const course = report.summary?.course || {};
  const counts = report.summary?.severity_counts || {};
  const outlier = report.summary?.possible_outlier;

  return (
    <section className="report">
      <div className="report-header">
        <div>
          <h3>Reporte comparativo</h3>
        </div>
        <span className="time">{report.processing_time_seconds}s</span>
      </div>

      <div className="severity-summary">
        <span>Críticas: {counts.Crítica || 0}</span>
        <span>Moderadas: {counts.Moderada || 0}</span>
        <span>Menores: {counts.Menor || 0}</span>
      </div>

      {outlier && (
        <div className="outlier">
          <AlertTriangle size={18} aria-hidden="true" />
          NRC {outlier.nrc} se aleja más del patrón del grupo ({outlier.alerts} alertas).
        </div>
      )}

      {report.inconsistencies.length === 0 ? (
        <p className="message ok">No se detectaron inconsistencias principales para los apartados del MVP.</p>
      ) : (
        <div className="report-table">
          <table>
            <thead>
              <tr>
                <th>Apartado</th>
                <th>Variable</th>
                <th>Diferencia detectada</th>
                <th>NRC</th>
                <th>Gravedad</th>
                <th>Sugerencia</th>
              </tr>
            </thead>
            <tbody>
              {report.inconsistencies.map((item) => (
                <tr key={item.id}>
                  <td>{item.section}</td>
                  <td>{item.variable}</td>
                  <td>{item.difference}</td>
                  <td>{item.involved_nrcs.join(", ")}</td>
                  <td><SeverityBadge severity={item.severity} /></td>
                  <td>{item.suggestion}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function App() {
  const [courses, setCourses] = useState([]);
  const [selectedCourse, setSelectedCourse] = useState(null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState(null);

  async function refreshCourses(selectCourseId = selectedCourse?.id) {
    setLoading(true);
    setError(null);
    try {
      const response = await listCourses();
      setCourses(response);
      if (selectCourseId) {
        await selectCourse(selectCourseId, false);
      }
    } catch (exc) {
      setError(exc.message);
    } finally {
      setLoading(false);
    }
  }

  async function selectCourse(courseId, clearReport = true) {
    setError(null);
    if (clearReport) setReport(null);
    try {
      const course = await getCourse(courseId);
      setSelectedCourse(course);
    } catch (exc) {
      setError(exc.message);
    }
  }

  async function handleAnalyze() {
    if (!selectedCourse) return;
    setAnalyzing(true);
    setError(null);
    try {
      const response = await analyzeCourse(selectedCourse.id);
      setReport(response);
      await refreshCourses(selectedCourse.id);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setAnalyzing(false);
    }
  }

  async function loadLatestReport() {
    if (!selectedCourse) return;
    setError(null);
    try {
      const response = await getLatestReport(selectedCourse.id);
      setReport(response);
    } catch (exc) {
      setError(exc.message);
    }
  }

  useEffect(() => {
    refreshCourses(null);
  }, []);

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <h1>Revisión comparativa de syllabus</h1>
        </div>
        <button className="ghost-button" onClick={() => refreshCourses()} disabled={loading}>
          {loading ? <Loader2 className="spin" size={18} /> : <RefreshCcw size={18} />}
          Actualizar
        </button>
      </header>

      <UploadPanel onUploaded={(courseId) => refreshCourses(courseId)} />

      {error && <p className="message error">{error}</p>}

      <div className="workspace">
        <CourseTable
          courses={courses}
          selectedCourseId={selectedCourse?.id}
          onSelect={selectCourse}
        />
        <CourseDetail
          course={selectedCourse}
          report={report}
          analyzing={analyzing}
          onAnalyze={handleAnalyze}
          onLoadReport={loadLatestReport}
        />
      </div>
    </main>
  );
}

