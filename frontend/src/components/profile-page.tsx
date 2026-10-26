"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, CalendarDays, CircleUserRound, LogOut, ShieldCheck } from "lucide-react";
import { useSyncExternalStore } from "react";

import { getProfile, requestJson } from "@/lib/api";
import { clearAccessToken, getAccessToken, hasAccessToken, subscribeToAuth } from "@/lib/auth-session";
import { Brand } from "@/components/brand";

export function ProfilePage() {
  const router = useRouter();
  const authenticated = useSyncExternalStore(subscribeToAuth, hasAccessToken, () => false);
  const accessToken = useSyncExternalStore(subscribeToAuth, getAccessToken, () => "");
  const profileQuery = useQuery({ queryKey: ["profile", accessToken], queryFn: () => getProfile(accessToken), enabled: Boolean(accessToken) });
  const logoutMutation = useMutation({
    mutationFn: () => requestJson<void>("/auth/logout", {}, accessToken),
    onSuccess: () => {
      clearAccessToken();
      router.push("/");
    },
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
        {logoutMutation.isError && <p className="profile-error" role="alert">{logoutMutation.error.message}</p>}
      </>}
    </section>
  </main>;
}