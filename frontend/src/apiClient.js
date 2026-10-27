// Access code is requested at runtime, never compiled into the public JS bundle.
const SESSION_KEY = 'digital-shadow-demo-access';

export async function apiFetch(url, options = {}) {
  const originalHeaders = options.headers || {};
  const send = (token) => fetch(url, {
    ...options,
    headers: { ...originalHeaders, ...(token ? { 'X-Demo-Access': token } : {}) },
  });

  let token = '';
  try { token = sessionStorage.getItem(SESSION_KEY) || ''; } catch { /* storage may be unavailable */ }
  let response = await send(token);
  if (response.status !== 401) return response;
  if (typeof window === 'undefined' || typeof window.prompt !== 'function') return response;

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const entered = window.prompt(attempt === 0
      ? 'This judging demo is access-protected. Enter the demo access code provided by the project owner.'
      : 'That code was not accepted. Try again.');
    if (entered === null || !entered.trim()) return response;
    token = entered.trim();
    try { sessionStorage.setItem(SESSION_KEY, token); } catch { /* continue without persistence */ }
    response = await send(token);
    if (response.status !== 401) return response;
    try { sessionStorage.removeItem(SESSION_KEY); } catch { /* ignore */ }
  }
  return response;
}
