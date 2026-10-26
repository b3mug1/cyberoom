"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ArrowLeft, ArrowRight, Gamepad2 } from "lucide-react";
import { getProfile, requestJson } from "@/lib/api";
import { saveAccessToken } from "@/lib/auth-session";
import { Brand } from "@/components/brand";

type AccessToken = { access_token: string };
const authSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password.").max(128),
  username: z.string().optional(),
  full_name: z.string().optional(),
}).superRefine((values, context) => {
  if (values.password.length < 12 && values.username !== undefined) {
    context.addIssue({ code: "custom", path: ["password"], message: "Use at least 12 characters." });
  }
  if (values.username !== undefined && !/^[a-zA-Z0-9_.-]{3,40}$/.test(values.username)) {
    context.addIssue({ code: "custom", path: ["username"], message: "Use 3-40 letters, numbers, dots, dashes, or underscores." });
  }
  if (values.full_name !== undefined && values.full_name.trim().length < 2) {
    context.addIssue({ code: "custom", path: ["full_name"], message: "Enter at least 2 characters." });
  }
});
type AuthValues = z.infer<typeof authSchema>;

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [registered, setRegistered] = useState(false);
  const register = mode === "register";
  const form = useForm<AuthValues>({ resolver: zodResolver(authSchema) });

  async function submit(values: AuthValues) {
    setPending(true);
    setError("");
    const payload = register
      ? { email: values.email, username: values.username, full_name: values.full_name, password: values.password }
      : { email: values.email, password: values.password };
    try {
      const tokens = await requestJson<AccessToken>(`/auth/${mode}`, payload);
      saveAccessToken(tokens.access_token);
      if (register) {
        setRegistered(true);
      } else {
        const profile = await getProfile(tokens.access_token);
        router.push(profile.role === "USER" ? "/" : "/dashboard");
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to sign in right now.");
    } finally {
      setPending(false);
    }
  }

  return <main className="auth-page">
    <div className="auth-visual"><Image fill priority sizes="(max-width: 720px) 100vw, 55vw" src="https://images.unsplash.com/photo-1542751371-adc38448a05e?auto=format&fit=crop&w=1300&q=90" alt="Gaming club arena" /><div className="auth-image-shade" /><Brand size="lg" /><div className="auth-visual-copy"><div className="eyebrow"><span className="live-dot" /> THE GAME STARTS BEFORE YOU ARRIVE</div><h1>{register ? <>Make room<br />for <em>more play.</em></> : <>Good to<br />have you <em>back.</em></>}</h1><p>Book better sessions with the places and PCs you actually want to play on.</p></div><span className="auth-image-label">CYBEROOM / PLAYER ACCESS</span></div>
    <section className="auth-panel"><Link href="/" className="auth-back"><ArrowLeft size={15} /> Back to explore</Link><div className="auth-form-wrap"><div className="eyebrow">PLAYER ACCESS <span>· 0{register ? "1" : "2"}</span></div>{registered ? <div className="registration-success" role="status"><span className="success-mark"><Gamepad2 size={20} /></span><h2>Account created.</h2><p>Your Cyberoom account is ready. You’re signed in and can book a session now.</p><Link className="auth-submit" href="/bookings">View my bookings <ArrowRight size={16} /></Link><Link className="success-secondary" href="/">Explore clubs</Link></div> : <><h2>{register ? "Create your account" : "Welcome back"}</h2><p className="auth-lede">{register ? "A few details and your next session is closer." : "Sign in to find your bookings and get back in the game."}</p>
      <form className="auth-form" onSubmit={form.handleSubmit(submit)}>
        {register && <><label>FULL NAME<input {...form.register("full_name")} autoComplete="name" maxLength={120} placeholder="Your name" />{form.formState.errors.full_name && <small>{form.formState.errors.full_name.message}</small>}</label><label>USERNAME<input {...form.register("username")} autoComplete="username" maxLength={40} placeholder="player_one" />{form.formState.errors.username && <small>{form.formState.errors.username.message}</small>}</label></>}
        <label>EMAIL ADDRESS<input {...form.register("email")} type="email" autoComplete="email" placeholder="you@example.com" />{form.formState.errors.email && <small>{form.formState.errors.email.message}</small>}</label>
        <label>PASSWORD<input {...form.register("password")} type="password" autoComplete={register ? "new-password" : "current-password"} maxLength={128} placeholder={register ? "At least 12 characters" : "Your password"} />{form.formState.errors.password && <small>{form.formState.errors.password.message}</small>}</label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="auth-submit" disabled={pending}>{pending ? "One moment..." : register ? "Create account" : "Sign in"}<ArrowRight size={16} /></button>
      </form>
      <p className="auth-switch">{register ? "Already have an account?" : "New to Cyberoom?"} <Link href={register ? "/login" : "/register"}>{register ? "Sign in" : "Create an account"}</Link></p>
      <p className="auth-terms">By continuing, you agree to keep your account details secure.</p>
    </>}</div></section>
  </main>;
}