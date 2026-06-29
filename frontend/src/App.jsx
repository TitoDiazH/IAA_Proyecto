import { ArrowLeft, BookOpen } from "lucide-react";
import { useEffect, useState } from "react";
import {
  analyzeCourse,
  getConditionsExportTable,
  getCourse,
  getLatestReport,
  listCourses,
} from "./api";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import Login from "./views/Login";
import Course from "./views/Course";
import Homepage from "./views/Homepage";

const HOME_CACHE_KEY = "iaa_home_v1";
const COURSE_CACHE_KEY = "iaa_course_v1";

function readHomeCache() {
  try {
    const raw = localStorage.getItem(HOME_CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeHomeCache(courses, exportTable) {
  try {
    localStorage.setItem(HOME_CACHE_KEY, JSON.stringify({ courses, exportTable }));
  } catch {}
}

function readCourseCache(courseId) {
  try {
    const raw = localStorage.getItem(COURSE_CACHE_KEY);
    if (!raw) return null;
    const cached = JSON.parse(raw);
    return String(cached?.courseId) === String(courseId) ? cached : null;
  } catch {
    return null;
  }
}

function writeCourseCache(courseId, course, report) {
  try {
    localStorage.setItem(COURSE_CACHE_KEY, JSON.stringify({ courseId: String(courseId), course, report }));
  } catch {}
}

function clearAllCache() {
  try {
    localStorage.removeItem(HOME_CACHE_KEY);
    localStorage.removeItem(COURSE_CACHE_KEY);
  } catch {}
}

function AppNav({ user, isHome, onBack, signOut }) {
  return (
    <nav className="app-nav" aria-label="Navegación principal">
      <div className="app-nav-start">
        {isHome ? (
          <span className="app-nav-brand">
            <BookOpen size={17} aria-hidden="true" />
            Revisión de Syllabus
          </span>
        ) : (
          <button type="button" className="app-nav-back" onClick={onBack}>
            <ArrowLeft size={16} aria-hidden="true" />
            Todos los cursos
          </button>
        )}
      </div>
      <div className="app-nav-end">
        <span className="app-nav-email">{user.email}</span>
        <button type="button" className="ghost-button app-nav-logout" onClick={signOut}>
          Cerrar sesión
        </button>
      </div>
    </nav>
  );
}

const HOME_ROUTE = { view: "home" };

function parseRoute() {
  const pathname = window.location.pathname.replace(/\/+$/, "") || "/";
  const params = new URLSearchParams(window.location.search);
  const queryCourseId = params.get("id");

  if (pathname === "/" || pathname === "/home") {
    return HOME_ROUTE;
  }

  const courseMatch = pathname.match(/^\/courses(?:\/(?:id=)?([^/]+))?$/);
  const courseId = courseMatch?.[1] || queryCourseId;
  if (courseId) {
    return { view: "course", courseId: decodeURIComponent(courseId) };
  }

  return HOME_ROUTE;
}

function routePath(route) {
  if (route.view === "course") {
    return `/courses/id=${encodeURIComponent(route.courseId)}`;
  }
  return "/home";
}

function updateBrowserRoute(route, { replace = false } = {}) {
  const nextPath = routePath(route);
  if (`${window.location.pathname}${window.location.search}` === nextPath) return;

  const method = replace ? "replaceState" : "pushState";
  window.history[method](null, "", nextPath);
}

function AppContent() {
  const { user, loading, signOut } = useAuth();

  const [route, setRoute] = useState(parseRoute);
  const [courses, setCourses] = useState(() => readHomeCache()?.courses ?? []);
  const [exportTable, setExportTable] = useState(() => readHomeCache()?.exportTable ?? null);
  const [activeCourse, setActiveCourse] = useState(() => {
    const r = parseRoute();
    return r.view === "course" ? (readCourseCache(r.courseId)?.course ?? null) : null;
  });
  const [report, setReport] = useState(() => {
    const r = parseRoute();
    return r.view === "course" ? (readCourseCache(r.courseId)?.report ?? null) : null;
  });
  const [loadingCourses, setLoadingCourses] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(() => {
    const r = parseRoute();
    return r.view === "course" ? !readCourseCache(r.courseId)?.course : false;
  });
  const [retryingAnalysis, setRetryingAnalysis] = useState(false);
  const [error, setError] = useState(null);

  async function refreshCourses() {
    setLoadingCourses(true);
    setError(null);
    try {
      const [data, table] = await Promise.all([
        listCourses(),
        getConditionsExportTable(),
      ]);
      setCourses(data);
      setExportTable(table);
      writeHomeCache(data, table);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setLoadingCourses(false);
    }
  }

  async function loadCourse(courseId) {
    const hasCached = activeCourse && String(activeCourse.id) === String(courseId);
    if (!hasCached) {
      setActiveCourse(null);
      setReport(null);
      setLoadingDetail(true);
    }
    setError(null);
    try {
      const course = await getCourse(courseId);
      setActiveCourse(course);
      if (course.latest_report_id) {
        try {
          const latestReport = await getLatestReport(courseId);
          setReport(latestReport);
          writeCourseCache(courseId, course, latestReport);
        } catch (exc) {
          setError(exc.message);
        }
      } else {
        writeCourseCache(courseId, course, null);
      }
    } catch (exc) {
      setError(exc.message);
      setRoute(HOME_ROUTE);
      updateBrowserRoute(HOME_ROUTE, { replace: true });
    } finally {
      setLoadingDetail(false);
    }
  }

  function openCourse(courseId) {
    const nextRoute = { view: "course", courseId: String(courseId) };
    setRoute(nextRoute);
    updateBrowserRoute(nextRoute);
    loadCourse(courseId);
  }

  function goHome() {
    setRoute(HOME_ROUTE);
    updateBrowserRoute(HOME_ROUTE);
    setActiveCourse(null);
    setReport(null);
    refreshCourses();
  }

  async function handleAnalyze() {
    if (!activeCourse) return;

    setRetryingAnalysis(true);
    setError(null);
    try {
      const queuedReport = await analyzeCourse(activeCourse.id);
      const updatedCourse = await getCourse(activeCourse.id);
      setReport(queuedReport);
      setActiveCourse(updatedCourse);
      refreshCourses();
    } catch (exc) {
      setError(exc.message);
    } finally {
      setRetryingAnalysis(false);
    }
  }

  useEffect(() => {
    if (!user) return;
    const initialRoute = parseRoute();
    setRoute(initialRoute);
    updateBrowserRoute(initialRoute, { replace: true });
    refreshCourses();

    if (initialRoute.view === "course") {
      loadCourse(initialRoute.courseId);
    }

    function handlePopState() {
      const nextRoute = parseRoute();
      setRoute(nextRoute);

      if (nextRoute.view === "course") {
        loadCourse(nextRoute.courseId);
      } else {
        setActiveCourse(null);
        setReport(null);
        refreshCourses();
      }
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [user]);

  useEffect(() => {
    const hasActiveAnalysis = courses.some((course) =>
      ["queued", "processing"].includes(course.latest_report_status)
    );
    if (!hasActiveAnalysis) return undefined;

    const interval = window.setInterval(refreshCourses, 5000);
    return () => window.clearInterval(interval);
  }, [courses]);

  useEffect(() => {
    if (route.view !== "course" || !activeCourse) return undefined;

    const status = report?.status || activeCourse.latest_report_status;
    if (!["queued", "processing"].includes(status)) return undefined;

    const interval = window.setInterval(async () => {
      try {
        const [updatedCourse, latestReport] = await Promise.all([
          getCourse(activeCourse.id),
          getLatestReport(activeCourse.id),
        ]);
        setActiveCourse(updatedCourse);
        setReport(latestReport);
      } catch (exc) {
        setError(exc.message);
      }
    }, 5000);

    return () => window.clearInterval(interval);
  }, [activeCourse, report?.status, route.view]);

  if (loading) {
    return <div className="auth-loading">Cargando…</div>;
  }

  if (!user) {
    return <Login />;
  }

  return (
    <div className="app-shell">
      <AppNav
        user={user}
        isHome={route.view === "home"}
        onBack={goHome}
        signOut={() => { clearAllCache(); signOut(); }}
      />

      {error && (
        <div className="global-error">
          <p className="message error">{error}</p>
        </div>
      )}

      {route.view === "home" ? (
        <Homepage
          courses={courses}
          exportTable={exportTable}
          loading={loadingCourses}
          onOpenCourse={openCourse}
          onRefresh={refreshCourses}
        />
      ) : (
        <Course
          course={activeCourse}
          report={report}
          loading={loadingDetail}
          retryingAnalysis={retryingAnalysis}
          onBack={goHome}
          onAnalyze={handleAnalyze}
        />
      )}
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
