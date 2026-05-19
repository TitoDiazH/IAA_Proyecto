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

export function syllabusDownloadUrl(syllabusId) {
  return `${API_BASE}/courses/syllabi/${syllabusId}/download`;
}

