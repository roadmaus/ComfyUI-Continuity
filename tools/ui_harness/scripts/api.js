// Stand-in for ComfyUI's scripts/api.js: same surface the pack touches, no server.
class Api extends EventTarget {
  clientId = "harness";
  initialClientId = "harness";
  apiURL(path) { return path; }
  fetchApi(path, options) { return fetch(path, options); }
  async queuePrompt() { return {}; }
  async interrupt() {}
  async getUserData() { return new Response("{}", { status: 404 }); }
  async storeUserData() { return new Response("{}"); }
  async deleteUserData() { return new Response("{}"); }
}
export const api = new Api();
