import { supabase } from "./supabase";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

async function getAuthHeader() {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token
    ? { Authorization: `Bearer ${session.access_token}` }
    : {};
}

async function request(path, options = {}) {
  const authHeader = await getAuthHeader();
  const headers = { ...authHeader, ...options.headers };

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (response.status === 401) {
    await supabase.auth.signOut();
    return;
  }

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
  const authHeader = await getAuthHeader();
  const params = new URLSearchParams({
    format,
    filename: filename || "condiciones-aprobacion",
  });
  const response = await fetch(
    `${API_BASE}/exports/conditions/download?${params}`,
    { headers: authHeader }
  );
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

export { getAuthHeader };
