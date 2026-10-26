"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Bell, CalendarDays, Check, CircleUserRound, Clock3, LogOut, ShieldCheck, Trash2 } from "lucide-react";
import { useSyncExternalStore } from "react";

import { authenticatedRequest, getMemberships, getNotifications, getProfile, getWaitlist, requestJson } from "@/lib/api";
import { clearAccessToken, getAccessToken, hasAccessToken, subscribeToAuth } from "@/lib/auth-session";
import { Brand } from "@/components/brand";

export function ProfilePage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const authenticated = useSyncExternalStore(subscribeToAuth, hasAccessToken, () => false);
  const accessToken = useSyncExternalStore(subscribeToAuth, getAccessToken, () => "");
  const profileQuery = useQuery({ queryKey: ["profile", accessToken], queryFn: () => getProfile(accessToken), enabled: Boolean(accessToken) });
  const notificationsQuery = useQuery({ queryKey: ["notifications", accessToken], queryFn: () => getNotifications(accessToken), enabled: Boolean(accessToken), refetchInterval: 60_000 });
  const waitlistQuery = useQuery({ queryKey: ["waitlist", accessToken], queryFn: () => getWaitlist(accessToken), enabled: Boolean(accessToken) });
  const membershipsQuery = useQuery({ queryKey: ["memberships", accessToken], queryFn: () => getMemberships(accessToken), enabled: Boolean(accessToken) });
  const logoutMutation = useMutation({
    mutationFn: () => requestJson<void>("/auth/logout", {}, accessToken),
    onSuccess: () => {
      clearAccessToken();
      router.push("/");
    },
  });
  const markReadMutation = useMutation({
    mutationFn: (id: string) => authenticatedRequest(`/notifications/${id}/read`, accessToken, "PATCH", {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications", accessToken] }),
  });
  const cancelWaitlistMutation = useMutation({
    mutationFn: (id: string) => authenticatedRequest(`/waitlist/${id}`, accessToken, "DELETE"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["waitlist", accessToken] }),
  });

  return <main className="profile-page">
    <header className="detail-top"><Brand size="md" /><Link className="back-link" href="/"><ArrowLeft size={15} /> Explore clubs</Link></header>
    <section className="profile-content"><div className="eyebrow">PLAYER SPACE / ACCOUNT</div><h1>Your profile.</h1>
      {!authenticated && <div className="profile-message"><CircleUserRound size={22} /><div><strong>You’re signed out.</strong><span>Sign in to see your account details.</span></div><Link href="/login">Sign in <ArrowRight size={15} /></Link></div>}
      {profileQuery.isPending && authenticated && <div className="result-state"><div className="loading-line" /><span>Loading your profile...</span></div>}
      {profileQuery.isError && <div className="profile-message"><ShieldCheck size={22} /><div><strong>Could not load your profile.</strong><span>{profileQuery.error.message}</span></div><Link href="/login">Sign in again <ArrowRight size={15} /></Link></div>}
      {profileQuery.data && <>
        <article className="profile-card"><div className="profile-avatar"><CircleUserRound size={29} /></div><div className="profile-identity"><h2>{profileQuery.data.full_name}</h2><p>@{profileQuery.data.username}</p></div><span className="role-label">{profileQuery.data.role}</span>
          <dl className="profile-fields"><div><dt>Email</dt><dd>{profileQuery.data.email}</dd></div><div><dt>Username</dt><dd>{profileQuery.data.username}</dd></div><div><dt>Account role</dt><dd>{profileQuery.data.role}</dd></div></dl>
        </article>
        <div className="profile-actions">{profileQuery.data.role !== "USER" && <Link href="/dashboard"><ShieldCheck size={16} /> Role dashboard <ArrowRight size={15} /></Link>}<Link href="/bookings"><CalendarDays size={16} /> My bookings <ArrowRight size={15} /></Link><button type="button" disabled={logoutMutation.isPending} onClick={() => logoutMutation.mutate()}><LogOut size={16} /> {logoutMutation.isPending ? "Signing out..." : "Sign out"}</button></div>
        <section className="profile-inbox"><div className="profile-section-heading"><div><div className="eyebrow">PLAYER UPDATES</div><h2><Bell size={18} /> Notifications</h2></div><span>{notificationsQuery.data?.filter((item) => !item.read_at).length ?? 0} unread</span></div>
          {notificationsQuery.isError && <p className="profile-error" role="alert">{notificationsQuery.error.message}</p>}
          {notificationsQuery.isPending && <p className="profile-muted">Loading notifications...</p>}
          {notificationsQuery.data?.length === 0 && <p className="profile-muted">No notifications yet. Booking updates and reminders will appear here.</p>}
          {notificationsQuery.data?.map((item) => <article className={`notification-item${item.read_at ? "" : " notification-unread"}`} key={item.id}><div><strong>{item.title}</strong><p>{item.message}</p><time>{new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.scheduled_at))}</time></div><div className="notification-item-actions">{item.booking_id && <Link href={`/booking/${item.booking_id}`}>Open booking <ArrowRight size={13} /></Link>}{item.payload.club_id && item.kind === "WAITLIST_AVAILABLE" && <Link href={`/clubs/${item.payload.club_id}`}>Check club <ArrowRight size={13} /></Link>}{!item.read_at && <button type="button" aria-label="Mark notification as read" disabled={markReadMutation.isPending} onClick={() => markReadMutation.mutate(item.id)}><Check size={15} /></button>}</div></article>)}
        </section>
        <section className="profile-inbox"><div className="profile-section-heading"><div><div className="eyebrow">PREPAID HOURS</div><h2><Clock3 size={18} /> Memberships</h2></div><span>{membershipsQuery.data?.filter((item) => item.remaining_minutes > 0 && Date.parse(item.expires_at) > Date.now()).length ?? 0} active</span></div>
          {membershipsQuery.isError && <p className="profile-error" role="alert">{membershipsQuery.error.message}</p>}
          {membershipsQuery.data?.length === 0 && <p className="profile-muted">No hour packs yet. Browse a club to see available memberships.</p>}
          {membershipsQuery.data?.map((item) => <article className="waitlist-item" key={item.id}><div><strong>{item.plan_name} · {item.club_name}</strong><p>{(item.remaining_minutes / 60).toLocaleString("ru-RU")} of {item.total_minutes / 60} hours left · expires {new Date(item.expires_at).toLocaleDateString("ru-RU")}</p></div><div className="notification-item-actions"><Link href={`/clubs/${item.club_id}`}>Use at club <ArrowRight size={13} /></Link></div></article>)}
        </section>
        <section className="profile-inbox"><div className="profile-section-heading"><div><div className="eyebrow">SAVED AVAILABILITY</div><h2><Clock3 size={18} /> Waitlist requests</h2></div><span>{waitlistQuery.data?.filter((item) => item.status !== "CANCELLED").length ?? 0} active</span></div>
          {waitlistQuery.isError && <p className="profile-error" role="alert">{waitlistQuery.error.message}</p>}
          {waitlistQuery.data?.length === 0 && <p className="profile-muted">No waitlist requests. Join one from a club page when all computers are booked.</p>}
          {waitlistQuery.data?.map((item) => <article className="waitlist-item" key={item.id}><div><strong>{item.status === "NOTIFIED" ? "A slot may have opened" : item.status === "CANCELLED" ? "Request cancelled" : "Waiting for a slot"}</strong><p>{new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.start_time))} – {new Intl.DateTimeFormat("ru-RU", { timeStyle: "short" }).format(new Date(item.end_time))}</p></div><div className="notification-item-actions"><Link href={`/clubs/${item.club_id}`}>Open club <ArrowRight size={13} /></Link>{item.status !== "CANCELLED" && <button type="button" aria-label="Cancel waitlist request" disabled={cancelWaitlistMutation.isPending} onClick={() => cancelWaitlistMutation.mutate(item.id)}><Trash2 size={15} /></button>}</div></article>)}
        </section>
        {logoutMutation.isError && <p className="profile-error" role="alert">{logoutMutation.error.message}</p>}
      </>}
    </section>
  </main>;
}
