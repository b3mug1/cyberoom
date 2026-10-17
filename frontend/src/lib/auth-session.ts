const authChangedEvent = "cyberbook:auth-changed";

export function subscribeToAuth(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener(authChangedEvent, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(authChangedEvent, callback);
  };
}

export function hasAccessToken() {
  return Boolean(window.sessionStorage.getItem("cyberbook.access"));
}

export function getAccessToken() {
  return window.sessionStorage.getItem("cyberbook.access") ?? "";
}

export function saveAccessToken(token: string) {
  window.sessionStorage.setItem("cyberbook.access", token);
  window.dispatchEvent(new Event(authChangedEvent));
}

export function clearAccessToken() {
  window.sessionStorage.removeItem("cyberbook.access");
  window.dispatchEvent(new Event(authChangedEvent));
}