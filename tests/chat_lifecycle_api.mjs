
// Added to layout's ComfyUI API stub. Everything under web/ remains unchanged.
const listeners = new Map();
export const lifecycle = {
  calls: [],
  http: async () => undefined,
  beforeWrite: async () => {},
  emit(type, detail) { api.dispatchEvent({ type, detail }); },
};
const fetchApi = api.fetchApi.bind(api);
const storeUserData = api.storeUserData.bind(api);
Object.assign(api, {
  clientId: "test-client",
  addEventListener(name, listener) {
    if (!listeners.has(name)) listeners.set(name, new Set());
    listeners.get(name).add(listener);
  },
  removeEventListener(name, listener) { listeners.get(name)?.delete(listener); },
  dispatchEvent(event) { for (const fn of [...(listeners.get(event.type) ?? [])]) fn(event); },
  async fetchApi(route, options) {
    lifecycle.calls.push({ route, options });
    return await lifecycle.http(route, options) ?? fetchApi(route, options);
  },
  async storeUserData(file, body) {
    await lifecycle.beforeWrite(file, body);
    return storeUserData(file, body);
  },
  interrupt() { throw new Error("Cancellation must never issue a global interrupt"); },
});
Object.assign(globalThis.__settings, { chat: { setup: true }, refiner: { model: "test-model" } });
