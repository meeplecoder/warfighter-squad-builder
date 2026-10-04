/* Thin wrapper over fetch() for the Warfighter Squad Builder API */
const API = {
  async request(method, path, body) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    let res;
    try {
      res = await fetch('/api' + path, opts);
    } catch (e) {
      throw { status: 0, error: 'Could not reach the server. Check your connection.' };
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw { status: res.status, error: data.error || 'Server error', data };
    return data;
  },
  get(path) { return this.request('GET', path); },
  post(path, body) { return this.request('POST', path, body); },
  put(path, body) { return this.request('PUT', path, body); },
  delete(path) { return this.request('DELETE', path); },
};
