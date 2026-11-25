// The dashboard's JSON API (api.py)

async function request(method, url, body, options = {}) {
  const init = { method, ...options };
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(body);
  }
  const response = await fetch(url, init);
  let data = null;
  try {
    data = await response.json();
  } catch {
    // not JSON (e.g. the app is restarting)
  }
  if (!response.ok) throw new Error((data && data.error) || `${response.status} ${response.statusText}`);
  return data;
}

// Sends a file as the raw request body (see upload_image in api.py)
async function upload(url, file) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream', 'X-Filename': encodeURIComponent(file.name) },
    body: file,
  });
  let data = null;
  try {
    data = await response.json();
  } catch {
    // not JSON
  }
  if (!response.ok) throw new Error((data && data.error) || `${response.status} ${response.statusText}`);
  return data;
}

export const api = {
  state: () => request('GET', '/api/state'),
  saveConfig: (config, options) => request('PUT', '/api/config', config, options),
  render: (widgets, known) => request('POST', '/api/render', { widgets, known }),
  live: () => request('GET', '/api/live'),
  show: screenId => request('POST', '/api/show', { screen_id: screenId }),
  brightness: value => request('PUT', '/api/brightness', { value }),
  images: () => request('GET', '/api/images'),
  uploadImage: file => upload('/api/images', file),
  deleteImage: id => request('DELETE', `/api/images/${id}`),
};
