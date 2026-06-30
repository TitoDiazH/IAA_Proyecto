import { ArrowLeft, BookOpen, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  analyzeCourse,
  deleteCourse,
  getConditionsExportTable,
  getCourse,
  getLatestReport,
  listCourses,
} from "./api";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { currentPeriod } from "./periods";
import Login from "./views/Login";
import Course from "./views/Course";
import Homepage from "./views/Homepage";

const HOME_CACHE_KEY = "iaa_home_v2";
const COURSE_CACHE_KEY = "iaa_course_v1";
const TOAST_DURATION_MS = 7000;
const TOAST_FADE_DURATION_MS = 300;

function readHomeCache() {
  try {
    const raw = localStorage.getItem(HOME_CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeHomeCache(courses, exportTable, selectedPeriod) {
  try {
    localStorage.setItem(HOME_CACHE_KEY, JSON.stringify({ courses, exportTable, selectedPeriod }));
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

// Keeps `rows` and `row_periods` in lockstep when filtering the conditions table.
function filterTableRows(table, predicate) {
  if (!table?.rows?.length) return table;
  const keepIndexes = table.rows.map((_, i) => i).filter((i) => predicate(table.rows[i], i));
  return {
    ...table,
    rows: keepIndexes.map((i) => table.rows[i]),
    row_periods: keepIndexes.map((i) => table.row_periods?.[i]),
    row_count: keepIndexes.length,
  };
}

function filterTableByPeriod(table, period) {
  // Defensive fallback: if the table predates row_periods (stale cache or an
  // older backend response), show all rows instead of silently filtering
  // everything out.
  if (!Array.isArray(table?.row_periods) || table.row_periods.length !== table?.rows?.length) {
    return table;
  }
  return filterTableRows(table, (_, i) => table.row_periods[i] === period);
}

function ToastContainer({ toasts, onDismiss }) {
  if (!toasts.length) return null;
  return (
    <div className="toast-container" aria-live="polite">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`toast toast-${toast.type}${toast.isExiting ? " toast-exiting" : ""}`}
          role="alert"
        >
          <span className="toast-message">{toast.message}</span>
          <button
            type="button"
            className="toast-close"
            onClick={() => onDismiss(toast.id)}
            aria-label="Cerrar"
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
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
  const [selectedPeriod, setSelectedPeriod] = useState(() => readHomeCache()?.selectedPeriod || currentPeriod());
  const selectedPeriodRef = useRef(selectedPeriod);
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
  const [toasts, setToasts] = useState([]);
  // Track in-flight deletes so refreshCourses() can't restore them from stale API data.
  const pendingDeleteIds = useRef(new Set());         // Set<String(courseId)>
  const pendingDeleteCodes = useRef(new Map());       // Map<course_code, refCount>

  function addToast(type, message) {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, type, message, isExiting: false }]);
    setTimeout(() => {
      setToasts((prev) => prev.map((toast) => (
        toast.id === id ? { ...toast, isExiting: true } : toast
      )));
    }, TOAST_DURATION_MS);
    setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
    }, TOAST_DURATION_MS + TOAST_FADE_DURATION_MS);
  }

  function dismissToast(id) {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }

  function notifyQuotaFailures(previousCourses, nextCourses) {
    const previousStatusById = new Map(previousCourses.map((c) => [String(c.id), c.latest_report_status]));
    for (const course of nextCourses) {
      const prevStatus = previousStatusById.get(String(course.id));
      const justFailed =
        ["queued", "processing"].includes(prevStatus) && course.latest_report_status === "failed";
      if (justFailed && course.latest_report_error_type === "quota_exceeded") {
        addToast(
          "error",
          `${course.course_name}: se agotó la cuota de la IA. Intenta el análisis más tarde.`
        );
      }
    }
  }

  async function refreshCourses(uploadResult = null) {
    // If the upload response includes course data, show cards immediately
    if (uploadResult?.courses?.length > 0) {
      setCourses((prev) => {
        const map = new Map(prev.map((c) => [c.id, c]));
        for (const c of uploadResult.courses) map.set(c.id, c);
        return [...map.values()].sort((a, b) => {
          const p = b.academic_period.localeCompare(a.academic_period);
          return p !== 0 ? p : a.course_code.localeCompare(b.course_code);
        });
      });
    }

    if (!uploadResult) setLoadingCourses(true);
    setError(null);
    let freshCourses = null;
    try {
      freshCourses = await listCourses();
      // Filter out courses whose delete is still in flight to avoid restoring them
      const visible = pendingDeleteIds.current.size
        ? freshCourses.filter((c) => !pendingDeleteIds.current.has(String(c.id)))
        : freshCourses;
      notifyQuotaFailures(courses, visible);
      setCourses(visible);
      writeHomeCache(visible, exportTable, selectedPeriodRef.current);
    } catch (exc) {
      if (!uploadResult) setError(exc.message);
      setLoadingCourses(false);
      return;
    }
    setLoadingCourses(false);
    // export table is secondary — failure must not block course display
    // Fetched once across all periods (each row is tagged via row_periods) so
    // switching periods afterwards is an instant client-side filter, not a refetch.
    try {
      const table = await getConditionsExportTable();
      // Filter out rows for courses whose delete is still in flight
      const filteredTable = pendingDeleteCodes.current.size
        ? filterTableRows(table, (r) => !pendingDeleteCodes.current.has(r[1]))
        : table;
      setExportTable(filteredTable);
      writeHomeCache(freshCourses, filteredTable, selectedPeriodRef.current);
    } catch {
      // silent — export table is best-effort
    }
  }

  function changePeriod(nextPeriod) {
    selectedPeriodRef.current = nextPeriod;
    setSelectedPeriod(nextPeriod);
    writeHomeCache(courses, exportTable, nextPeriod);
  }

  function _addPendingCode(code) {
    pendingDeleteCodes.current.set(code, (pendingDeleteCodes.current.get(code) ?? 0) + 1);
  }
  function _removePendingCode(code) {
    const n = pendingDeleteCodes.current.get(code) ?? 0;
    if (n <= 1) pendingDeleteCodes.current.delete(code);
    else pendingDeleteCodes.current.set(code, n - 1);
  }

  function _filterExportTable(table, codes) {
    if (!codes.length) return table;
    const codeSet = new Set(codes);
    return filterTableRows(table, (r) => !codeSet.has(r[1]));
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

  function handleDeleteCourse(courseId) {
    const key = String(courseId);
    const removed = courses.find((c) => String(c.id) === key);
    const code = removed?.course_code;

    pendingDeleteIds.current.add(key);
    if (code) _addPendingCode(code);

    const updatedCourses = courses.filter((c) => String(c.id) !== key);
    const updatedTable = _filterExportTable(exportTable, code ? [code] : []);
    setCourses(updatedCourses);
    if (updatedTable !== exportTable) setExportTable(updatedTable);
    writeHomeCache(updatedCourses, updatedTable, selectedPeriodRef.current);
    localStorage.removeItem(COURSE_CACHE_KEY);

    deleteCourse(courseId)
      .then(() => addToast("ok", "Curso eliminado correctamente"))
      .catch((exc) => {
        if (removed) {
          setCourses((prev) => {
            const ids = new Set(prev.map((c) => String(c.id)));
            return ids.has(key) ? prev : [...prev, removed];
          });
        }
        addToast("error", exc.message);
      })
      .finally(() => {
        pendingDeleteIds.current.delete(key);
        if (code) _removePendingCode(code);
      });
  }

  function handleDeleteMany(courseIds) {
    const idSet = new Set(courseIds.map(String));
    const removedMap = new Map(
      courses.filter((c) => idSet.has(String(c.id))).map((c) => [String(c.id), c])
    );
    const deletedCodes = [...removedMap.values()].map((c) => c.course_code).filter(Boolean);

    idSet.forEach((id) => pendingDeleteIds.current.add(id));
    deletedCodes.forEach((code) => _addPendingCode(code));

    const updatedCourses = courses.filter((c) => !idSet.has(String(c.id)));
    const updatedTable = _filterExportTable(exportTable, deletedCodes);
    setCourses(updatedCourses);
    if (updatedTable !== exportTable) setExportTable(updatedTable);
    writeHomeCache(updatedCourses, updatedTable, selectedPeriodRef.current);
    localStorage.removeItem(COURSE_CACHE_KEY);

    Promise.allSettled(courseIds.map((id) => deleteCourse(id))).then((results) => {
      const failedIds = courseIds.filter((_, i) => results[i].status === "rejected").map(String);
      const succeededIds = courseIds.filter((_, i) => results[i].status === "fulfilled").map(String);

      succeededIds.forEach((id) => {
        pendingDeleteIds.current.delete(id);
        const code = removedMap.get(id)?.course_code;
        if (code) _removePendingCode(code);
      });

      if (failedIds.length > 0) {
        const toRestore = failedIds.map((id) => removedMap.get(id)).filter(Boolean);
        failedIds.forEach((id) => {
          pendingDeleteIds.current.delete(id);
          const code = removedMap.get(id)?.course_code;
          if (code) _removePendingCode(code);
        });
        setCourses((prev) => {
          const existing = new Set(prev.map((c) => String(c.id)));
          return [...prev, ...toRestore.filter((c) => !existing.has(String(c.id)))];
        });
        addToast("error", `${failedIds.length} curso${failedIds.length !== 1 ? "s" : ""} no pudo eliminarse`);
      }

      const n = succeededIds.length;
      if (n > 0) addToast("ok", `${n} curso${n !== 1 ? "s" : ""} eliminado${n !== 1 ? "s" : ""}`);
    });
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
        const wasActive = ["queued", "processing"].includes(status);
        const [updatedCourse, latestReport] = await Promise.all([
          getCourse(activeCourse.id),
          getLatestReport(activeCourse.id),
        ]);
        setActiveCourse(updatedCourse);
        setReport(latestReport);
        if (wasActive && latestReport.status === "failed" && latestReport.summary?.error_type === "quota_exceeded") {
          addToast("error", "Se agotó la cuota de la IA. Intenta el análisis más tarde.");
        }
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

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />

      {error && (
        <div className="global-error">
          <p className="message error">{error}</p>
        </div>
      )}

      {route.view === "home" ? (
        <Homepage
          courses={courses.filter((c) => c.academic_period === selectedPeriod)}
          hasAnyCourses={courses.length > 0}
          exportTable={filterTableByPeriod(exportTable, selectedPeriod)}
          loading={loadingCourses}
          selectedPeriod={selectedPeriod}
          onPeriodChange={changePeriod}
          onOpenCourse={openCourse}
          onRefresh={refreshCourses}
          onDeleteCourse={handleDeleteCourse}
          onDeleteMany={handleDeleteMany}
          addToast={addToast}
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
