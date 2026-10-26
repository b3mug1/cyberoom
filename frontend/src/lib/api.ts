import type { Booking, Club, ClubPage, ClubReview, Membership, MembershipPlan, UserNotification, WaitlistRequest } from "@/types/api";
import { clearAccessToken, saveAccessToken } from "@/lib/auth-session";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function authenticatedFetch(url: string, accessToken: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${accessToken}`);
  let response = await fetch(url, { ...init, headers, credentials: "include" });
  if (response.status !== 401 || typeof window === "undefined") return response;

  const refreshResponse = await fetch(`${apiBase}/auth/refresh`, { method: "POST", credentials: "include" });
  if (!refreshResponse.ok) {
    clearAccessToken();
    return response;
  }
  const refreshed = await refreshResponse.json() as { access_token: string };
  saveAccessToken(refreshed.access_token);
  headers.set("Authorization", `Bearer ${refreshed.access_token}`);
  response = await fetch(url, { ...init, headers, credentials: "include" });
  return response;
}

export async function getClubs(search: string, city: string): Promise<ClubPage> {
  const query = new URLSearchParams({ page: "1", page_size: "12" });
  if (search.trim()) query.set("search", search.trim());
  if (city) query.set("city", city);
  const response = await fetch(`${apiBase}/clubs?${query}`, { cache: "no-store" });
  if (!response.ok) throw new Error("We couldn't load clubs. Check the connection and try again.");
  return response.json() as Promise<ClubPage>;
}

export async function getClub(clubId: string): Promise<Club> {
  const response = await fetch(`${apiBase}/clubs/${clubId}`, { cache: "no-store" });
  if (!response.ok) throw new Error(response.status === 404 ? "This club could not be found." : "We couldn't load this club.");
  return response.json() as Promise<Club>;
}

export async function getClubReviews(clubId: string): Promise<ClubReview[]> {
  const response = await fetch(`${apiBase}/clubs/${clubId}/reviews`, { cache: "no-store" });
  if (!response.ok) throw new Error("We couldn't load club reviews.");
  return response.json() as Promise<ClubReview[]>;
}

export async function getClubMembershipPlans(clubId: string): Promise<MembershipPlan[]> {
  const response = await fetch(`${apiBase}/clubs/${clubId}/membership-plans`, { cache: "no-store" });
  if (!response.ok) throw new Error("We couldn't load membership plans.");
  return response.json() as Promise<MembershipPlan[]>;
}

export async function getMemberships(accessToken: string): Promise<Membership[]> {
  return authenticatedRequest<Membership[]>("/memberships", accessToken, "GET");
}

export async function getBookings(accessToken: string): Promise<Booking[]> {
  const response = await authenticatedFetch(`${apiBase}/bookings`, accessToken, { cache: "no-store" });
  if (!response.ok) throw new Error("We couldn't load your bookings. Please sign in again.");
  return response.json() as Promise<Booking[]>;
}

export async function getNotifications(accessToken: string): Promise<UserNotification[]> {
  return authenticatedRequest<UserNotification[]>("/notifications", accessToken, "GET");
}

export async function getWaitlist(accessToken: string): Promise<WaitlistRequest[]> {
  return authenticatedRequest<WaitlistRequest[]>("/waitlist", accessToken, "GET");
}

export async function getBooking(bookingId: string, accessToken: string): Promise<Booking> {
  const response = await authenticatedFetch(`${apiBase}/bookings/${bookingId}`, accessToken, { cache: "no-store" });
  if (!response.ok) throw new Error(response.status === 404 ? "Booking not found." : "We couldn't load this booking.");
  return response.json() as Promise<Booking>;
}

export type Profile = { id: string; email: string; username: string; full_name: string; role: string };

export async function getProfile(accessToken: string): Promise<Profile> {
  const response = await authenticatedFetch(`${apiBase}/auth/me`, accessToken, { cache: "no-store" });
  if (!response.ok) throw new Error("Your session has expired. Please sign in again.");
  return response.json() as Promise<Profile>;
}

export async function authenticatedRequest<T>(
  path: string,
  accessToken: string,
  method: "GET" | "POST" | "PATCH" | "DELETE",
  body?: unknown,
): Promise<T> {
  const response = await authenticatedFetch(`${apiBase}${path}`, accessToken, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: method === "GET" ? "no-store" : undefined,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null) as { detail?: { message?: string } | string } | null;
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.message ?? "The request could not be completed.");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function requestJson<T>(path: string, body: unknown, accessToken?: string): Promise<T> {
  const request: RequestInit = {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  const response = accessToken
    ? await authenticatedFetch(`${apiBase}${path}`, accessToken, request)
    : await fetch(`${apiBase}${path}`, request);
  const data = await response.json().catch(() => null) as {
    detail?: { message?: string } | string | Array<{ loc?: Array<string | number>; msg?: string }>;
  } | null;
  if (!response.ok) {
    const detail = data?.detail;
    const message = typeof detail === "string"
      ? detail
      : Array.isArray(detail)
        ? detail.map((issue) => `${issue.loc?.at(-1) ?? "Request"}: ${issue.msg ?? "Invalid value."}`).join(" ")
        : detail?.message;
    throw new Error(message ?? "Your request could not be completed.");
  }
  return data as T;
}

export { apiBase };
