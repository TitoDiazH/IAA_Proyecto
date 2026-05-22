import { useEffect, useState } from "react";
import {
  analyzeCourse,
  getConditionsExportTable,
  getCourse,
  getLatestReport,
  listCourses,
} from "./api";
import Course from "./views/Course";
import Homepage from "./views/Homepage";

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

export default function App() {
  const [route, setRoute] = useState(parseRoute);
  const [courses, setCourses] = useState([]);
  const [exportTable, setExportTable] = useState(null);
  const [activeCourse, setActiveCourse] = useState(null);
  const [report, setReport] = useState(null);
  const [loadingCourses, setLoadingCourses] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
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
    } catch (exc) {
      setError(exc.message);
    } finally {
      setLoadingCourses(false);
    }
  }

  async function loadCourse(courseId) {
    setLoadingDetail(true);
    setReport(null);
    setError(null);
    try {
      const course = await getCourse(courseId);
      setActiveCourse(course);
      if (course.latest_report_id) {
        try {
          const latestReport = await getLatestReport(courseId);
          setReport(latestReport);
        } catch (exc) {
          setError(exc.message);
        }
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
  }, []);

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

  return (
    <div className="app-shell">
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
