const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    let detail = "Error inesperado";
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      detail = response.statusText;
    }
    throw new Error(detail);
  }
  return response.json();
}

export function listCourses() {
  return request("/courses");
}

export function getCourse(courseId) {
  return request(`/courses/${courseId}`);
}

export function analyzeCourse(courseId) {
  return request(`/courses/${courseId}/analyze`, { method: "POST" });
}

export function getLatestReport(courseId) {
  return request(`/courses/${courseId}/report/latest`);
}

export function uploadZip(file) {
  const body = new FormData();
  body.append("file", file);
  return request("/uploads/zip", { method: "POST", body });
}

export function getConditionsExportTable() {
  return request("/exports/conditions");
}

export async function downloadConditionsExport({ format, filename }) {
  const params = new URLSearchParams({
    format,
    filename: filename || "condiciones-aprobacion",
  });
  const response = await fetch(`${API_BASE}/exports/conditions/download?${params}`);
  if (!response.ok) {
    throw new Error(response.statusText || "No se pudo exportar la tabla");
  }
  return response.blob();
}

export function syllabusDownloadUrl(syllabusId) {
  return `${API_BASE}/courses/syllabi/${syllabusId}/download`;
}

export function syllabusViewUrl(syllabusId) {
  return `${API_BASE}/courses/syllabi/${syllabusId}/view`;
}
