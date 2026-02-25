// Shared API helper for admin modules (FX, slot rules, etc.)
(function () {
  function getApiBase() { return (window.API_BASE || localStorage.getItem("FSB_API_BASE") || "").replace(/\/$/, ""); }
  function getToken() { return localStorage.getItem("FSB_TOKEN") || ""; }
  async function refreshAccessToken() {
    var base = getApiBase(), ref = localStorage.getItem("FSB_REFRESH_TOKEN");
    if (!base || !ref) return false;
    try {
      var r = await fetch(base + "/auth/refresh?refresh_token=" + encodeURIComponent(ref), { method: "POST", headers: { "Content-Type": "application/json" } });
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
        if (res.status === 401) throw new Error("Session expired or invalid. Please sign in again from the login page.");
        throw new Error(text || res.statusText);
      }
      return await res.json();
    }
  };
})();
