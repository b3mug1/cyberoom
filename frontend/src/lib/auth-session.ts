const authChangedEvent = "cyberoom:auth-changed";

export function subscribeToAuth(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener(authChangedEvent, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(authChangedEvent, callback);
  };
}

export function hasAccessToken() {
  return Boolean(window.sessionStorage.getItem("cyberoom.access"));
}

export function getAccessToken() {
  return window.sessionStorage.getItem("cyberoom.access") ?? "";
}

export function saveAccessToken(token: string) {
  window.sessionStorage.setItem("cyberoom.access", token);
  window.dispatchEvent(new Event(authChangedEvent));
}

export function clearAccessToken() {
  window.sessionStorage.removeItem("cyberoom.access");
  window.dispatchEvent(new Event(authChangedEvent));
}