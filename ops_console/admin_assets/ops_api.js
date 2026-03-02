// Shared API helper for admin modules (FX, slot rules, etc.)
(function () {
  function esc(s) { if (s == null || s === undefined) return ""; var d = document.createElement("div"); d.textContent = String(s); return d.innerHTML; }
  function escAttr(s) { if (s == null || s === undefined) return ""; return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#39;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  window.FSB_esc = esc;
  window.FSB_escAttr = escAttr;

  function getApiBase() { return (window.API_BASE || localStorage.getItem("FSB_API_BASE") || "").replace(/\/$/, ""); }
  function getToken() { return localStorage.getItem("FSB_TOKEN") || ""; }
  function clearSessionAndRedirectToLogin() {
    localStorage.removeItem("FSB_TOKEN");
    localStorage.removeItem("FSB_REFRESH_TOKEN");
    var isModule = /admin_modules\//.test(window.location.pathname || "");
    top.location.href = isModule ? "../login.html" : "login.html";
  }
  async function refreshAccessToken() {
    var base = getApiBase(), ref = localStorage.getItem("FSB_REFRESH_TOKEN");
    if (!base || !ref) return false;
    try {
      var r = await fetch(base + "/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: ref })
      });
      if (!r.ok) return false;
      var data = await r.json();
      if (data.access_token) {
        localStorage.setItem("FSB_TOKEN", data.access_token);
        if (data.refresh_token) localStorage.setItem("FSB_REFRESH_TOKEN", data.refresh_token);
        return true;
      }
    } catch (e) {}
    return false;
  }
  window.OpsApi = {
    async fetch(method, path, body, _retried) {
      var base = getApiBase(), token = getToken();
      if (!base) throw new Error("API_BASE not set. Sign in from the login page.");
      var res = await fetch(base + path, {
        method,
        headers: { "Content-Type": "application/json", ...(token ? { "Authorization": "Bearer " + token } : {}) },
        body: body ? JSON.stringify(body) : undefined
      });
      if (res.status === 401 && !_retried && await refreshAccessToken()) return window.OpsApi.fetch(method, path, body, true);
      if (!res.ok) {
        var text = await res.text();
        if (res.status === 401) {
          clearSessionAndRedirectToLogin();
          throw new Error("Session expired. Redirecting to login.");
        }
        throw new Error(text || res.statusText);
      }
      return await res.json();
    }
  };
  window.FSB_clearSessionAndRedirectToLogin = clearSessionAndRedirectToLogin;
  window.FSB_refreshToken = refreshAccessToken;
})();
