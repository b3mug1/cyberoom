"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, useSyncExternalStore, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, Building2, Cpu, Gauge, ShieldCheck, Users } from "lucide-react";

import { authenticatedRequest, getProfile } from "@/lib/api";
import { getAccessToken, hasAccessToken, subscribeToAuth } from "@/lib/auth-session";
import type { Booking, Club, Computer } from "@/types/api";

type Profile = Awaited<ReturnType<typeof getProfile>>;
type StaffBooking = Booking & { club_id: string; club_name: string; customer_name: string; customer_email: string | null; computer_name: string };
type OwnerStats = { club_count: number; computer_count: number; active_computers: number; maintenance_computers: number; bookings_today: number; revenue_today: string };
type OwnerData = { summary: OwnerStats; clubs: Club[]; bookings: StaffBooking[] };
type StaffComputer = Computer & { club_id: string; club_name: string };
type StaffData = { assigned_clubs: number; bookings_today: number; upcoming_bookings: number; active_sessions: number; bookings: StaffBooking[]; computers: StaffComputer[] };
type ClubAvailability = { computers: Array<{ computer_id: string; busy: Array<{ start_time: string; end_time: string }> }> };

function futureEnd(minutes: number, from = Date.now()) {
  return new Date((Math.ceil(from / 60_000) + minutes) * 60_000).toISOString();
}
function extensionEnd(minutes: number, bookedEnd: string) {
  return futureEnd(minutes, Math.max(Date.now(), Date.parse(bookedEnd)));
}
type AdminSummary = { users: number; active_users: number; clubs: number; active_clubs: number; computers: number; active_computers: number; bookings_today: number; revenue_today: string };
type AdminUser = { id: string; email: string; username: string; full_name: string; role: string; is_active: boolean; created_at: string };
type AdminClub = Club & { owner_id: string; is_active: boolean };
type AdminData = { summary: AdminSummary; users: AdminUser[]; clubs: AdminClub[]; bookings: StaffBooking[] };

async function loadRoleData<T>(token: string, role: Profile["role"]): Promise<T> {
  if (role === "OWNER") {
    const [summary, clubs, bookings] = await Promise.all([
      authenticatedRequest<OwnerStats>("/owner/dashboard", token, "GET"),
      authenticatedRequest<Club[]>("/owner/clubs", token, "GET"),
      authenticatedRequest<StaffBooking[]>("/owner/bookings", token, "GET"),
    ]);
    return { summary, clubs, bookings } as T;
  }
  if (role === "STAFF") {
    const [summary, computers] = await Promise.all([
      authenticatedRequest<Omit<StaffData, "computers">>("/staff/dashboard", token, "GET"),
      authenticatedRequest<StaffComputer[]>("/staff/computers", token, "GET"),
    ]);
    return { ...summary, computers } as T;
  }
  const [summary, users, clubs, bookings] = await Promise.all([
    authenticatedRequest<AdminSummary>("/admin/dashboard", token, "GET"),
    authenticatedRequest<AdminUser[]>("/admin/users?page=1&page_size=100", token, "GET"),
    authenticatedRequest<AdminClub[]>("/admin/clubs", token, "GET"),
    authenticatedRequest<StaffBooking[]>("/admin/bookings", token, "GET"),
  ]);
  return { summary, users, clubs, bookings } as T;
}

function DashboardFrame({ profile, children }: { profile: Profile; children: React.ReactNode }) {
  return <main className="role-dashboard"><header className="detail-top"><Link className="brand" href="/"><span className="brand-mark">CB</span><span>cyber<span>book</span></span></Link><Link className="back-link" href="/profile"><ArrowLeft size={15} /> Profile</Link></header><section className="role-content"><div className="role-heading"><div><div className="eyebrow">CONTROL ROOM / {profile.role}</div><h1>{profile.role === "OWNER" ? "Your venues." : profile.role === "STAFF" ? "Today’s floor." : "Platform overview."}</h1><p>{profile.full_name} <span>·</span> {profile.role.toLowerCase()}</p></div><span className="role-mark">{profile.role}</span></div>{children}</section></main>;
}

function StatStrip({ values }: { values: Array<{ label: string; value: string | number }> }) {
  return <div className="role-stats">{values.map((item) => <div className="role-stat" key={item.label}><span>{item.label}</span><strong>{item.value}</strong></div>)}</div>;
}

function RoleMessage({ title, message, href = "/login", action = "Sign in" }: { title: string; message: string; href?: string; action?: string }) {
  return <main className="role-message-page"><div><ShieldCheck size={24} /><h1>{title}</h1><p>{message}</p><Link href={href}>{action} <ArrowRight size={15} /></Link></div></main>;
}

function OwnerPanel({ token }: { token: string }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["role-dashboard", "OWNER", token], queryFn: () => loadRoleData<OwnerData>(token, "OWNER") });
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: "POST" | "PATCH"; body: unknown }) => authenticatedRequest(path, token, method, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["role-dashboard", "OWNER", token] }),
  });
  if (query.isPending) return <div className="role-loading">Loading your clubs...</div>;
  if (query.isError || !query.data) return <div className="role-error" role="alert">{query.error?.message ?? "Owner dashboard unavailable."}</div>;
  const { summary, clubs, bookings } = query.data;
  const clubOptions = clubs.map((club) => <option key={club.id} value={club.id}>{club.name}</option>);

  function submit(path: string, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body: Record<string, unknown> = Object.fromEntries(data.entries());
    const selectedClub = String(data.get("club_id") ?? "");
    const endpoint = path.replace(":club", selectedClub);
    for (const key of ["ram_gb", "refresh_rate"]) if (key in body) body[key] = Number(body[key]);
    if ("price_per_hour" in body) body.price_per_hour = Number(body.price_per_hour);
    mutation.mutate({ path: endpoint, method: "POST", body });
    event.currentTarget.reset();
  }

  return <>
    <StatStrip values={[{ label: "CLUBS", value: summary.club_count }, { label: "COMPUTERS", value: summary.computer_count }, { label: "MAINTENANCE", value: summary.maintenance_computers }, { label: "TODAY’S BOOKINGS", value: summary.bookings_today }, { label: "TODAY’S REVENUE", value: `${Number(summary.revenue_today).toLocaleString("en-US")} KZT` }]} />
    {mutation.isError && <p className="role-error" role="alert">{mutation.error.message}</p>}{mutation.isSuccess && <p className="role-success" role="status">Changes saved.</p>}
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">YOUR BUSINESS</div><h2>Managed clubs</h2></div><span>{clubs.length} venues</span></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club</th><th>City</th><th>Time zone</th><th>Computers</th><th>Tariffs</th><th>State</th></tr></thead><tbody>{clubs.map((club) => <tr key={club.id}><td><strong>{club.name}</strong></td><td>{club.city}</td><td><form onSubmit={(event) => { event.preventDefault(); const timezone = String(new FormData(event.currentTarget).get("timezone") ?? ""); mutation.mutate({ path: `/owner/clubs/${club.id}`, method: "PATCH", body: { timezone } }); }}><input name="timezone" aria-label={`${club.name} IANA time zone`} defaultValue={club.timezone} required /><button className="table-action" disabled={mutation.isPending}>Save</button></form></td><td>{club.computers.length}</td><td>{club.tariffs.length}</td><td>{club.is_active ? "Active" : "Paused"}</td></tr>)}</tbody></table>{clubs.length === 0 && <p className="role-empty">Create your first club below.</p>}</div></section>
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">HARDWARE</div><h2>Computer availability</h2></div></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club</th><th>Station</th><th>GPU</th><th>State</th></tr></thead><tbody>{clubs.flatMap((club) => club.computers.map((computer) => <tr key={computer.id}><td>{club.name}</td><td>{computer.name}</td><td>{computer.gpu}</td><td><select value={computer.status} onChange={(event) => mutation.mutate({ path: `/owner/computers/${computer.id}/status`, method: "PATCH", body: { status: event.target.value } })}><option value="AVAILABLE">Available</option>{computer.status === "OCCUPIED" && <option value="OCCUPIED" disabled>Occupied by booking</option>}<option value="MAINTENANCE">Maintenance</option><option value="DISABLED">Disabled</option></select></td></tr>))}</tbody></table>{clubs.every((club) => club.computers.length === 0) && <p className="role-empty">No computers have been added yet.</p>}</div></section>
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">OPERATIONS</div><h2>Add venue resources</h2></div></div><div className="role-form-grid">
      <form className="role-form" onSubmit={(event) => submit("/owner/clubs", event)}><h3><Building2 size={16} /> New club</h3><input name="name" required minLength={2} placeholder="Club name" /><input name="city" required placeholder="City" /><input name="timezone" required defaultValue="Asia/Almaty" aria-label="Club IANA time zone" placeholder="IANA time zone (Asia/Almaty)" /><input name="address" required placeholder="Street address" /><input name="phone" placeholder="Phone" /><textarea name="description" placeholder="Description" /><button disabled={mutation.isPending}>Create club <ArrowRight size={14} /></button></form>
      {clubs.length > 0 && <>
        <form className="role-form" onSubmit={(event) => submit("/owner/clubs/:club/computers", event)}><h3><Cpu size={16} /> Add computer</h3><select name="club_id" required defaultValue="">{<option value="" disabled>Select a club</option>}{clubOptions}</select><input name="name" required placeholder="Station name" /><input name="cpu" required placeholder="CPU" /><input name="gpu" required placeholder="GPU" /><input name="ram_gb" type="number" min="1" required placeholder="RAM in GB" /><input name="storage" required placeholder="Storage" /><input name="monitor" placeholder="Monitor" /><input name="refresh_rate" type="number" min="30" defaultValue="240" required placeholder="Refresh rate" /><button disabled={mutation.isPending}>Add computer <ArrowRight size={14} /></button></form>
        <form className="role-form" onSubmit={(event) => submit("/owner/clubs/:club/tariffs", event)}><h3><Gauge size={16} /> Add tariff</h3><select name="club_id" required defaultValue="">{<option value="" disabled>Select a club</option>}{clubOptions}</select><input name="name" required placeholder="Tariff name" /><input name="price_per_hour" type="number" min="1" required placeholder="Price per hour (KZT)" /><label>Starts<input name="start_time" type="time" required /></label><label>Ends<input name="end_time" type="time" required /></label><button disabled={mutation.isPending}>Add tariff <ArrowRight size={14} /></button></form>
        <form className="role-form" onSubmit={(event) => submit("/owner/clubs/:club/staff", event)}><h3><Users size={16} /> Assign staff</h3><select name="club_id" required defaultValue="">{<option value="" disabled>Select a club</option>}{clubOptions}</select><input name="email" type="email" required placeholder="Staff account email" /><button disabled={mutation.isPending}>Assign staff member <ArrowRight size={14} /></button></form>
      </>}
    </div></section>
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">RESERVATIONS</div><h2>Recent bookings</h2></div><span>{bookings.length} shown</span></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club</th><th>Customer</th><th>Computer</th><th>Start</th><th>Status</th><th>Total</th></tr></thead><tbody>{bookings.slice(0, 30).map((booking) => <tr key={booking.id}><td>{booking.club_name}</td><td>{booking.customer_name}</td><td>{booking.computer_name}</td><td>{new Date(booking.start_time).toLocaleString()}</td><td>{booking.status}</td><td>{Number(booking.total_price).toLocaleString()} KZT</td></tr>)}</tbody></table>{bookings.length === 0 && <p className="role-empty">No bookings yet.</p>}</div></section>
  </>;
}

function StaffPanel({ token }: { token: string }) {
  const queryClient = useQueryClient();
  const [qrToken, setQrToken] = useState("");
  const [verifiedBooking, setVerifiedBooking] = useState<StaffBooking | null>(null);
  const [selectedComputerId, setSelectedComputerId] = useState("");
  const [guestName, setGuestName] = useState("");
  const [duration, setDuration] = useState(60);
  const query = useQuery({ queryKey: ["role-dashboard", "STAFF", token], queryFn: () => loadRoleData<StaffData>(token, "STAFF"), refetchInterval: 30_000 });
  const selectedComputer = query.data?.computers.find((computer) => computer.id === selectedComputerId) ?? query.data?.computers[0];
  const availability = useQuery({
    queryKey: ["staff-availability", selectedComputer?.club_id],
    queryFn: () => {
      const start = new Date();
      const params = new URLSearchParams({ start_time: start.toISOString(), end_time: futureEnd(8 * 60) });
      return authenticatedRequest<ClubAvailability>(`/clubs/${selectedComputer!.club_id}/availability?${params}`, token, "GET");
    },
    enabled: Boolean(selectedComputer),
    refetchInterval: 30_000,
  });
  const busy = availability.data?.computers.find((computer) => computer.computer_id === selectedComputer?.id)?.busy ?? [];
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: "POST" | "PATCH"; body?: unknown }) => authenticatedRequest(path, token, method, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["role-dashboard", "STAFF", token] });
      void queryClient.invalidateQueries({ queryKey: ["staff-availability"] });
    },
  });
  const qrMutation = useMutation({
    mutationFn: (value: string) => authenticatedRequest<StaffBooking>("/staff/bookings/verify-qr", token, "POST", { qr_token: value }),
    onSuccess: setVerifiedBooking,
  });
  if (query.isPending) return <div className="role-loading">Loading assigned clubs...</div>;
  if (query.isError || !query.data) return <div className="role-error" role="alert">{query.error?.message ?? "Staff dashboard unavailable."}</div>;
  const data = query.data;
  const overdue = data.bookings.filter((booking) => booking.status === "ACTIVE" && Date.parse(booking.end_time) <= query.dataUpdatedAt);
  async function verifyQr(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setVerifiedBooking(null);
    qrMutation.mutate(qrToken);
  }
  function seatGuest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedComputer) return;
    mutation.mutate({ path: "/staff/walk-ins", method: "POST", body: {
      computer_id: selectedComputer.id, guest_name: guestName.trim(), end_time: futureEnd(duration),
    } }, { onSuccess: () => setGuestName("") });
  }
  function extend(booking: StaffBooking, minutes: number) {
    mutation.mutate({ path: `/staff/bookings/${booking.id}/extend`, method: "POST", body: {
      end_time: extensionEnd(minutes, booking.end_time),
    } });
  }
  return <>
    <StatStrip values={[{ label: "ASSIGNED CLUBS", value: data.assigned_clubs }, { label: "TODAY’S BOOKINGS", value: data.bookings_today }, { label: "UPCOMING", value: data.upcoming_bookings }, { label: "ACTIVE SESSIONS", value: data.active_sessions }]} />
    {mutation.isError && <p className="role-error" role="alert">{mutation.error.message}</p>}{mutation.isSuccess && <p className="role-success" role="status">Action completed.</p>}
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">WALK-IN</div><h2>Seat a guest</h2></div></div>
      <div className="staff-booking-grid"><form className="role-form" onSubmit={seatGuest}>
        <h3>Start a session now</h3><input aria-label="Guest name" value={guestName} onChange={(event) => setGuestName(event.target.value)} required maxLength={120} placeholder="Guest name" />
        <select aria-label="Computer" value={selectedComputer?.id ?? ""} onChange={(event) => setSelectedComputerId(event.target.value)} required>{data.computers.map((computer) => <option key={computer.id} value={computer.id}>{computer.club_name} / {computer.name}</option>)}</select>
        <label>Duration<select value={duration} onChange={(event) => setDuration(Number(event.target.value))}>{[30, 60, 90, 120, 180, 240].map((minutes) => <option key={minutes} value={minutes}>{minutes} minutes</option>)}</select></label>
        <button disabled={!selectedComputer || mutation.isPending}>Seat guest <ArrowRight size={14} /></button>
      </form><div className="staff-availability"><div className="eyebrow">NEXT 8 HOURS</div><h3>{selectedComputer?.name ?? "Select a computer"}</h3>
        {availability.isPending && <p>Loading reservations...</p>}{availability.isError && <p className="role-error">{availability.error.message}</p>}
        {availability.isSuccess && busy.length === 0 && <p>No reserved intervals in this window.</p>}
        {busy.map((slot, index) => <div className="staff-busy-slot" key={`${slot.start_time}-${index}`}><span>{new Date(slot.start_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}–{new Date(slot.end_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span><strong>Reserved</strong></div>)}
      </div></div>
    </section>
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">CHECK-IN</div><h2>Verify a booking QR</h2></div></div><form className="qr-verify-form" onSubmit={verifyQr}><input value={qrToken} onChange={(event) => setQrToken(event.target.value)} required minLength={16} maxLength={64} placeholder="Scan or enter QR token" /><button disabled={qrMutation.isPending}>{qrMutation.isPending ? "Checking..." : "Verify"} <ArrowRight size={14} /></button></form>{qrMutation.isError && <p className="role-error" role="alert">{qrMutation.error.message}</p>}{verifiedBooking && <div className="verified-booking" role="status"><strong>{verifiedBooking.customer_name}</strong><span>{verifiedBooking.club_name} / {verifiedBooking.computer_name}</span><span>{new Date(verifiedBooking.start_time).toLocaleString()} · {verifiedBooking.status}</span></div>}</section>
    {overdue.length > 0 && <section className="role-section" aria-live="polite"><div className="role-section-head"><div><div className="eyebrow">ACTION REQUIRED</div><h2>Overdue sessions</h2></div><span>{overdue.length} need attention</span></div><p className="role-error">These computers remain unavailable for new bookings until the session is extended or ended.</p><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club / computer</th><th>Customer</th><th>Booked until</th><th>Action</th></tr></thead><tbody>{overdue.map((booking) => <tr key={booking.id}><td>{booking.club_name} / {booking.computer_name}</td><td>{booking.customer_name}</td><td>{new Date(booking.end_time).toLocaleString()}</td><td><div className="staff-row-actions"><button className="table-action" disabled={mutation.isPending} onClick={() => extend(booking, 5)}>+5 min</button><button className="table-action" disabled={mutation.isPending} onClick={() => extend(booking, 10)}>+10 min</button><button className="table-action" disabled={mutation.isPending} onClick={() => mutation.mutate({ path: `/staff/bookings/${booking.id}/end`, method: "POST" })}>End</button></div></td></tr>)}</tbody></table></div></section>}
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">CURRENT &amp; UPCOMING</div><h2>Booking queue</h2></div><span>{data.bookings.length} assigned sessions</span></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club</th><th>Customer</th><th>Computer</th><th>Time</th><th>Status</th><th>Action</th></tr></thead><tbody>{data.bookings.map((booking) => <tr key={booking.id}><td>{booking.club_name}</td><td>{booking.customer_name}<small>{booking.customer_email ?? booking.source.replace("_", " ")}</small></td><td>{booking.computer_name}</td><td>{new Date(booking.start_time).toLocaleString()}<small>Until {new Date(booking.end_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</small></td><td>{booking.status}</td><td><div className="staff-row-actions">{booking.status === "CONFIRMED" && <button className="table-action" disabled={mutation.isPending} onClick={() => mutation.mutate({ path: `/staff/bookings/${booking.id}/start`, method: "POST" })}>Start</button>}{booking.status === "ACTIVE" && <><button className="table-action" disabled={mutation.isPending} onClick={() => extend(booking, 30)}>+30 min</button><button className="table-action" disabled={mutation.isPending} onClick={() => mutation.mutate({ path: `/staff/bookings/${booking.id}/end`, method: "POST" })}>End</button></>}</div></td></tr>)}</tbody></table>{data.bookings.length === 0 && <p className="role-empty">No current or upcoming bookings are assigned to your clubs.</p>}</div></section>
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">FLOOR STATUS</div><h2>Assigned computers</h2></div></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club</th><th>Computer</th><th>CPU / GPU</th><th>Memory</th><th>Status</th></tr></thead><tbody>{data.computers.map((computer) => <tr key={computer.id}><td>{computer.club_name}</td><td>{computer.name}</td><td>{computer.cpu} / {computer.gpu}</td><td>{computer.ram_gb} GB</td><td><select value={computer.status} onChange={(event) => mutation.mutate({ path: `/staff/computers/${computer.id}/status`, method: "PATCH", body: { status: event.target.value } })}><option value="AVAILABLE">Available</option><option value="MAINTENANCE">Maintenance</option><option value="DISABLED">Disabled</option></select></td></tr>)}</tbody></table>{data.computers.length === 0 && <p className="role-empty">No computers are assigned to your clubs.</p>}</div></section>
  </>;
}

function AdminPanel({ token, profile }: { token: string; profile: Profile }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["role-dashboard", "ADMIN", token], queryFn: () => loadRoleData<AdminData>(token, "ADMIN") });
  const mutation = useMutation({
    mutationFn: ({ path, body }: { path: string; body: unknown }) => authenticatedRequest(path, token, "PATCH", body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["role-dashboard", "ADMIN", token] }),
  });
  if (query.isPending) return <div className="role-loading">Loading platform data...</div>;
  if (query.isError || !query.data) return <div className="role-error" role="alert">{query.error?.message ?? "Admin dashboard unavailable."}</div>;
  const { summary, users, clubs, bookings } = query.data;
  return <>
    <StatStrip values={[{ label: "USERS", value: summary.users }, { label: "ACTIVE USERS", value: summary.active_users }, { label: "CLUBS", value: summary.active_clubs }, { label: "ACTIVE COMPUTERS", value: summary.active_computers }, { label: "TODAY’S BOOKINGS", value: summary.bookings_today }, { label: "TODAY’S REVENUE", value: `${Number(summary.revenue_today).toLocaleString()} KZT` }]} />
    {mutation.isError && <p className="role-error" role="alert">{mutation.error.message}</p>}{mutation.isSuccess && <p className="role-success" role="status">Platform record updated.</p>}
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">PLATFORM ACCESS</div><h2>Users</h2></div><span>{users.length} shown</span></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Name</th><th>Email</th><th>Username</th><th>Role</th><th>State</th><th>Action</th></tr></thead><tbody>{users.map((account) => <tr key={account.id}><td>{account.full_name}</td><td>{account.email}</td><td>{account.username}</td><td>{account.role}</td><td>{account.is_active ? "Active" : "Suspended"}</td><td>{account.id === profile.id ? "Current admin" : <button className="table-action" onClick={() => mutation.mutate({ path: `/admin/users/${account.id}/status`, body: { is_active: !account.is_active } })}>{account.is_active ? "Suspend" : "Reactivate"}</button>}</td></tr>)}</tbody></table></div></section>
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">VENUES</div><h2>Clubs</h2></div><span>{clubs.length} shown</span></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club</th><th>City</th><th>Owner ID</th><th>Stations</th><th>State</th><th>Action</th></tr></thead><tbody>{clubs.map((club) => <tr key={club.id}><td>{club.name}</td><td>{club.city}</td><td>{club.owner_id.slice(0, 8)}</td><td>{club.computers.length}</td><td>{club.is_active ? "Active" : "Paused"}</td><td><button className="table-action" onClick={() => mutation.mutate({ path: `/admin/clubs/${club.id}/status`, body: { is_active: !club.is_active } })}>{club.is_active ? "Pause" : "Activate"}</button></td></tr>)}</tbody></table></div></section>
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">GLOBAL ACTIVITY</div><h2>Recent bookings</h2></div><span>{bookings.length} shown</span></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club</th><th>Customer</th><th>Computer</th><th>Start</th><th>Status</th><th>Total</th></tr></thead><tbody>{bookings.slice(0, 40).map((booking) => <tr key={booking.id}><td>{booking.club_name}</td><td>{booking.customer_name}</td><td>{booking.computer_name}</td><td>{new Date(booking.start_time).toLocaleString()}</td><td>{booking.status}</td><td>{Number(booking.total_price).toLocaleString()} KZT</td></tr>)}</tbody></table></div></section>
  </>;
}

export function RoleDashboard() {
  const authenticated = useSyncExternalStore(subscribeToAuth, hasAccessToken, () => false);
  const token = useSyncExternalStore(subscribeToAuth, getAccessToken, () => "");
  const profileQuery = useQuery({ queryKey: ["profile", token], queryFn: () => getProfile(token), enabled: Boolean(token) });
  if (!authenticated) return <RoleMessage title="Sign in to continue." message="Role dashboards are available to signed-in accounts." />;
  if (profileQuery.isPending) return <main className="role-message-page">Loading account...</main>;
  if (profileQuery.isError || !profileQuery.data) return <RoleMessage title="Session expired." message="Sign in again to access your role dashboard." />;
  const profile = profileQuery.data;
  if (profile.role === "USER") return <RoleMessage title="No management dashboard." message="USER accounts can browse clubs and manage bookings from their profile." href="/profile" action="Open profile" />;
  const content = profile.role === "OWNER" ? <OwnerPanel token={token} /> : profile.role === "STAFF" ? <StaffPanel token={token} /> : <AdminPanel token={token} profile={profile} />;
  return <DashboardFrame profile={profile}>{content}</DashboardFrame>;
}
