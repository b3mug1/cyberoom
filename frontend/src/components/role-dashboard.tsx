"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, useSyncExternalStore, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, Building2, Clock3, Cpu, Gauge, ShieldCheck, Users } from "lucide-react";

import { authenticatedRequest, getProfile } from "@/lib/api";
import { getAccessToken, hasAccessToken, subscribeToAuth } from "@/lib/auth-session";
import { Brand } from "@/components/brand";
import type { Booking, Club, Computer } from "@/types/api";

type Profile = Awaited<ReturnType<typeof getProfile>>;
type StaffBooking = { id: string; club_id: string; club_name: string; customer_name: string; customer_email: string | null; source: "ONLINE" | "WALK_IN"; computer_id: string; computer_name: string; start_time: string; end_time: string; status: Booking["status"]; total_price: string };
type OwnerStats = { club_count: number; computer_count: number; active_computers: number; maintenance_computers: number; bookings_today: number; revenue_today: string };
type AuditEvent = { id: string; actor_id: string | null; club_id: string | null; action: string; entity_type: string; entity_id: string; details: Record<string, unknown>; created_at: string };
type StaffShift = { id: string; club_id: string; club_name: string; staff_user_id: string; staff_name: string; staff_email: string; start_time: string; end_time: string; created_at: string };
type PromoCode = { id: string; club_id: string; code: string; discount_type: "PERCENT" | "FIXED"; discount_value: string; starts_at: string; ends_at: string; usage_limit: number | null; used_count: number; per_user_limit: number; is_active: boolean };
type MembershipPlan = { id: string; club_id: string; name: string; description: string; hours: number; price: string; validity_days: number; is_active: boolean };
type OwnerData = { summary: OwnerStats; clubs: Club[]; bookings: StaffBooking[]; audit: AuditEvent[]; shifts: StaffShift[]; promoCodes: PromoCode[]; membershipPlans: MembershipPlan[] };
type OwnerReport = { start_date: string; end_date: string; currency: string; bookings: number; booking_value: string; daily: Array<{ date: string; bookings: number; booking_value: string }>; hourly: Array<{ hour: number; bookings: number }>; computers: Array<{ computer_id: string; computer_name: string; bookings: number; booking_value: string }> };
type StaffComputer = Computer & { club_id: string; club_name: string };
type StaffData = { assigned_clubs: number; bookings_today: number; upcoming_bookings: number; active_sessions: number; bookings: StaffBooking[]; computers: StaffComputer[]; shifts: StaffShift[] };
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
type AdminData = { summary: AdminSummary; users: AdminUser[]; clubs: AdminClub[]; bookings: StaffBooking[]; audit: AuditEvent[] };

async function loadRoleData<T>(token: string, role: Profile["role"]): Promise<T> {
  if (role === "OWNER") {
    const [summary, clubs, bookings, audit, shifts, promoCodes, membershipPlans] = await Promise.all([
      authenticatedRequest<OwnerStats>("/owner/dashboard", token, "GET"),
      authenticatedRequest<Club[]>("/owner/clubs", token, "GET"),
      authenticatedRequest<StaffBooking[]>("/owner/bookings", token, "GET"),
      authenticatedRequest<AuditEvent[]>("/owner/audit?limit=100", token, "GET"),
      authenticatedRequest<StaffShift[]>("/owner/shifts?limit=100", token, "GET"),
      authenticatedRequest<PromoCode[]>("/owner/promo-codes", token, "GET"),
      authenticatedRequest<MembershipPlan[]>("/owner/membership-plans", token, "GET"),
    ]);
    return { summary, clubs, bookings, audit, shifts, promoCodes, membershipPlans } as T;
  }
  if (role === "STAFF") {
    const [summary, computers, shifts] = await Promise.all([
      authenticatedRequest<Omit<StaffData, "computers" | "shifts">>("/staff/dashboard", token, "GET"),
      authenticatedRequest<StaffComputer[]>("/staff/computers", token, "GET"),
      authenticatedRequest<StaffShift[]>("/staff/shifts?limit=100", token, "GET"),
    ]);
    return { ...summary, computers, shifts } as T;
  }
  const [summary, users, clubs, bookings, audit] = await Promise.all([
    authenticatedRequest<AdminSummary>("/admin/dashboard", token, "GET"),
    authenticatedRequest<AdminUser[]>("/admin/users?page=1&page_size=100", token, "GET"),
    authenticatedRequest<AdminClub[]>("/admin/clubs", token, "GET"),
    authenticatedRequest<StaffBooking[]>("/admin/bookings", token, "GET"),
    authenticatedRequest<AuditEvent[]>("/admin/audit?limit=100", token, "GET"),
  ]);
  return { summary, users, clubs, bookings, audit } as T;
}

function DashboardFrame({ profile, children }: { profile: Profile; children: React.ReactNode }) {
  return <main className="role-dashboard"><header className="detail-top"><Brand size="md" /><Link className="back-link" href="/profile"><ArrowLeft size={15} /> Profile</Link></header><section className="role-content"><div className="role-heading"><div><div className="eyebrow">CONTROL ROOM / {profile.role}</div><h1>{profile.role === "OWNER" ? "Your venues." : profile.role === "STAFF" ? "Today’s floor." : "Platform overview."}</h1><p>{profile.full_name} <span>·</span> {profile.role.toLowerCase()}</p></div><span className="role-mark">{profile.role}</span></div>{children}</section></main>;
}

function StatStrip({ values }: { values: Array<{ label: string; value: string | number }> }) {
  return <div className="role-stats">{values.map((item) => <div className="role-stat" key={item.label}><span>{item.label}</span><strong>{item.value}</strong></div>)}</div>;
}

function AuditSection({ entries }: { entries: AuditEvent[] }) {
  return <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">CHANGE HISTORY</div><h2>Recent actions</h2></div><span>{entries.length} shown</span></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>When</th><th>Action</th><th>Record</th><th>Actor ID</th></tr></thead><tbody>{entries.map((entry) => <tr key={entry.id}><td>{new Date(entry.created_at).toLocaleString()}</td><td>{entry.action.replaceAll("_", " ")}</td><td>{entry.entity_type} · {entry.entity_id.slice(0, 8)}</td><td>{entry.actor_id?.slice(0, 8) ?? "System"}</td></tr>)}</tbody></table>{entries.length === 0 && <p className="role-empty">No audited changes yet.</p>}</div></section>;
}

function RoleMessage({ title, message, href = "/login", action = "Sign in" }: { title: string; message: string; href?: string; action?: string }) {
  return <main className="role-message-page"><div><ShieldCheck size={24} /><h1>{title}</h1><p>{message}</p><Link href={href}>{action} <ArrowRight size={15} /></Link></div></main>;
}

function OwnerReportsPanel({ token }: { token: string }) {
  const [endDate, setEndDate] = useState("");
  const [startDate, setStartDate] = useState("");
  useEffect(() => {
    const end = new Date();
    const start = new Date(end.getTime() - 29 * 86_400_000);
    const asLocalDate = (value: Date) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
    setEndDate(asLocalDate(end));
    setStartDate(asLocalDate(start));
  }, []);
  const query = useQuery({
    queryKey: ["owner-report", token, startDate, endDate],
    queryFn: () => authenticatedRequest<OwnerReport>(`/owner/reports?${new URLSearchParams({ start_date: startDate, end_date: endDate })}`, token, "GET"),
    enabled: Boolean(startDate && endDate && startDate <= endDate),
  });
  const report = query.data;
  const maxDailyValue = Math.max(1, ...(report?.daily.map((item) => Number(item.booking_value)) ?? []));
  const maxHourlyBookings = Math.max(1, ...(report?.hourly.map((item) => item.bookings) ?? []));

  return <section className="role-section owner-reports">
    <div className="role-section-head"><div><div className="eyebrow">BUSINESS REPORT</div><h2>Bookings and booked value</h2></div><span>Values are based on reservations; payment totals are shown separately when a provider is connected.</span></div>
    <div className="report-filters"><label>From<input type="date" value={startDate} max={endDate} onChange={(event) => setStartDate(event.target.value)} /></label><label>To<input type="date" value={endDate} min={startDate} onChange={(event) => setEndDate(event.target.value)} /></label></div>
    {query.isError && <p className="role-error" role="alert">{query.error.message}</p>}
    {query.isPending && <p className="role-loading">Loading report...</p>}
    {report && <>
      <div className="report-summary"><div><span>BOOKINGS</span><strong>{report.bookings}</strong></div><div><span>BOOKED VALUE</span><strong>{Number(report.booking_value).toLocaleString("ru-RU")} {report.currency}</strong></div></div>
      <div className="report-charts">
        <div className="report-chart"><h3>Booked value by day</h3><div className="daily-chart">{report.daily.map((item) => <div className="daily-chart-column" key={item.date} title={`${item.date}: ${Number(item.booking_value).toLocaleString("ru-RU")} ${report.currency}, ${item.bookings} bookings`}><span style={{ height: `${Math.max(2, Number(item.booking_value) / maxDailyValue * 100)}%` }} /><small>{item.date.slice(5)}</small></div>)}</div></div>
        <div className="report-chart"><h3>Bookings by start hour</h3><div className="hourly-chart">{report.hourly.map((item) => <div className="hourly-chart-column" key={item.hour} title={`${item.hour}:00 · ${item.bookings} bookings`}><span style={{ height: `${Math.max(2, item.bookings / maxHourlyBookings * 100)}%` }} /><small>{item.hour}</small></div>)}</div></div>
      </div>
      <div className="role-table-wrap report-computers"><table className="role-table"><thead><tr><th>Computer</th><th>Bookings</th><th>Booked value</th></tr></thead><tbody>{report.computers.map((computer) => <tr key={computer.computer_id}><td>{computer.computer_name}</td><td>{computer.bookings}</td><td>{Number(computer.booking_value).toLocaleString("ru-RU")} {report.currency}</td></tr>)}</tbody></table>{report.computers.length === 0 && <p className="role-empty">No reservations in this date range.</p>}</div>
    </>}
  </section>;
}

function OwnerPanel({ token }: { token: string }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["role-dashboard", "OWNER", token], queryFn: () => loadRoleData<OwnerData>(token, "OWNER") });
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: "POST" | "PATCH" | "DELETE"; body?: unknown }) => authenticatedRequest(path, token, method, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["role-dashboard", "OWNER", token] }),
  });
  if (query.isPending) return <div className="role-loading">Loading your clubs...</div>;
  if (query.isError || !query.data) return <div className="role-error" role="alert">{query.error?.message ?? "Owner dashboard unavailable."}</div>;
  const { summary, clubs, bookings, audit, shifts, promoCodes, membershipPlans } = query.data;
  const clubOptions = clubs.map((club) => <option key={club.id} value={club.id}>{club.name}</option>);

  function submit(path: string, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body: Record<string, unknown> = Object.fromEntries(data.entries());
    const selectedClub = String(data.get("club_id") ?? "");
    const endpoint = path.replace(":club", selectedClub);
    if ("days_of_week" in body) body.days_of_week = data.getAll("days_of_week").map(Number);
    for (const key of ["ram_gb", "refresh_rate"]) if (key in body) body[key] = Number(body[key]);
    if ("price_per_hour" in body) body.price_per_hour = Number(body.price_per_hour);
    mutation.mutate({ path: endpoint, method: "POST", body });
    event.currentTarget.reset();
  }

  function scheduleShift(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const clubId = String(data.get("club_id") ?? "");
    mutation.mutate({
      path: `/owner/clubs/${clubId}/shifts`,
      method: "POST",
      body: {
        staff_email: String(data.get("staff_email") ?? ""),
        start_time: new Date(String(data.get("start_time"))).toISOString(),
        end_time: new Date(String(data.get("end_time"))).toISOString(),
      },
    });
    form.reset();
  }

  function createPromoCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const clubId = String(data.get("club_id") ?? "");
    mutation.mutate({
      path: `/owner/clubs/${clubId}/promo-codes`,
      method: "POST",
      body: {
        code: String(data.get("code") ?? "").trim().toUpperCase(),
        discount_type: String(data.get("discount_type") ?? "PERCENT"),
        discount_value: Number(data.get("discount_value")),
        starts_at: new Date(String(data.get("starts_at"))).toISOString(),
        ends_at: new Date(String(data.get("ends_at"))).toISOString(),
        usage_limit: data.get("usage_limit") ? Number(data.get("usage_limit")) : null,
        per_user_limit: Number(data.get("per_user_limit") || 1),
      },
    });
    form.reset();
  }

  function createMembershipPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const clubId = String(data.get("club_id") ?? "");
    mutation.mutate({
      path: `/owner/clubs/${clubId}/membership-plans`,
      method: "POST",
      body: {
        name: String(data.get("name") ?? "").trim(),
        description: String(data.get("description") ?? "").trim(),
        hours: Number(data.get("hours")),
        price: Number(data.get("price")),
        validity_days: Number(data.get("validity_days")),
      },
    });
    form.reset();
  }

  return <>
    <StatStrip values={[{ label: "CLUBS", value: summary.club_count }, { label: "COMPUTERS", value: summary.computer_count }, { label: "MAINTENANCE", value: summary.maintenance_computers }, { label: "TODAY’S BOOKINGS", value: summary.bookings_today }, { label: "TODAY’S BOOKED VALUE", value: `${Number(summary.revenue_today).toLocaleString("en-US")} KZT` }]} />
    <OwnerReportsPanel token={token} />
    {mutation.isError && <p className="role-error" role="alert">{mutation.error.message}</p>}{mutation.isSuccess && <p className="role-success" role="status">Changes saved.</p>}
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">YOUR BUSINESS</div><h2>Managed clubs</h2></div><span>{clubs.length} venues</span></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club</th><th>City</th><th>Time zone / refund cutoff</th><th>Computers</th><th>Tariffs</th><th>State</th></tr></thead><tbody>{clubs.map((club) => <tr key={club.id}><td><strong>{club.name}</strong></td><td>{club.city}</td><td><form className="club-policy-form" onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); mutation.mutate({ path: `/owner/clubs/${club.id}`, method: "PATCH", body: { timezone: String(data.get("timezone") ?? ""), refund_cutoff_hours: Number(data.get("refund_cutoff_hours")) } }); }}><input name="timezone" aria-label={`${club.name} IANA time zone`} defaultValue={club.timezone} required /><label>Refund before (hours)<input name="refund_cutoff_hours" type="number" min="0" max="720" defaultValue={club.refund_cutoff_hours} required /></label><button className="table-action" disabled={mutation.isPending}>Save</button></form></td><td>{club.computers.length}</td><td>{club.tariffs.length}</td><td>{club.is_active ? "Active" : "Paused"}</td></tr>)}</tbody></table>{clubs.length === 0 && <p className="role-empty">Create your first club below.</p>}</div></section>
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">HARDWARE</div><h2>Computer availability</h2></div></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club</th><th>Station</th><th>GPU</th><th>State</th></tr></thead><tbody>{clubs.flatMap((club) => club.computers.map((computer) => <tr key={computer.id}><td>{club.name}</td><td>{computer.name}</td><td>{computer.gpu}</td><td><select value={computer.status} onChange={(event) => mutation.mutate({ path: `/owner/computers/${computer.id}/status`, method: "PATCH", body: { status: event.target.value } })}><option value="AVAILABLE">Available</option>{computer.status === "OCCUPIED" && <option value="OCCUPIED" disabled>Occupied by booking</option>}<option value="MAINTENANCE">Maintenance</option><option value="DISABLED">Disabled</option></select></td></tr>))}</tbody></table>{clubs.every((club) => club.computers.length === 0) && <p className="role-empty">No computers have been added yet.</p>}</div></section>
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">OPERATIONS</div><h2>Add venue resources</h2></div></div><div className="role-form-grid">
      <form className="role-form" onSubmit={(event) => submit("/owner/clubs", event)}><h3><Building2 size={16} /> New club</h3><input name="name" required minLength={2} placeholder="Club name" /><input name="city" required placeholder="City" /><input name="timezone" required defaultValue="Asia/Almaty" aria-label="Club IANA time zone" placeholder="IANA time zone (Asia/Almaty)" /><input name="address" required placeholder="Street address" /><input name="phone" placeholder="Phone" /><textarea name="description" placeholder="Description" /><button disabled={mutation.isPending}>Create club <ArrowRight size={14} /></button></form>
      {clubs.length > 0 && <>
        <form className="role-form" onSubmit={(event) => submit("/owner/clubs/:club/computers", event)}><h3><Cpu size={16} /> Add computer</h3><select name="club_id" required defaultValue="">{<option value="" disabled>Select a club</option>}{clubOptions}</select><input name="name" required placeholder="Station name" /><input name="cpu" required placeholder="CPU" /><input name="gpu" required placeholder="GPU" /><input name="ram_gb" type="number" min="1" required placeholder="RAM in GB" /><input name="storage" required placeholder="Storage" /><input name="monitor" placeholder="Monitor" /><input name="refresh_rate" type="number" min="30" defaultValue="240" required placeholder="Refresh rate" /><button disabled={mutation.isPending}>Add computer <ArrowRight size={14} /></button></form>
        <form className="role-form" onSubmit={(event) => submit("/owner/clubs/:club/tariffs", event)}><h3><Gauge size={16} /> Add tariff</h3><select name="club_id" required defaultValue="">{<option value="" disabled>Select a club</option>}{clubOptions}</select><input name="name" required placeholder="Tariff name" /><input name="price_per_hour" type="number" min="1" required placeholder="Price per hour (KZT)" /><label>Starts<input name="start_time" type="time" required /></label><label>Ends<input name="end_time" type="time" required /></label><fieldset className="weekday-selector"><legend>Applies on</legend>{["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day, index) => <label key={day}><input type="checkbox" name="days_of_week" value={index} defaultChecked />{day}</label>)}</fieldset><button disabled={mutation.isPending}>Add tariff <ArrowRight size={14} /></button></form>
        <form className="role-form" onSubmit={(event) => submit("/owner/clubs/:club/staff", event)}><h3><Users size={16} /> Assign staff</h3><select name="club_id" required defaultValue="">{<option value="" disabled>Select a club</option>}{clubOptions}</select><input name="email" type="email" required placeholder="Staff account email" /><button disabled={mutation.isPending}>Assign staff member <ArrowRight size={14} /></button></form>
        <form className="role-form" onSubmit={scheduleShift}><h3><Clock3 size={16} /> Schedule staff shift</h3><select name="club_id" required defaultValue="">{<option value="" disabled>Select a club</option>}{clubOptions}</select><input name="staff_email" type="email" required placeholder="Assigned staff email" /><label>Starts<input name="start_time" type="datetime-local" required /></label><label>Ends<input name="end_time" type="datetime-local" required /></label><button disabled={mutation.isPending}>Create shift <ArrowRight size={14} /></button></form>
      </>}
    </div></section>
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">PROMOTIONS</div><h2>Promo codes</h2></div><span>{promoCodes.length} configured</span></div>
      <div className="role-form-grid">{clubs.length > 0 && <form className="role-form" onSubmit={createPromoCode}><h3>Create a promo code</h3><select name="club_id" required defaultValue=""><option value="" disabled>Select a club</option>{clubOptions}</select><input name="code" required minLength={3} maxLength={32} pattern="[A-Za-z0-9_-]+" placeholder="Code (e.g. NIGHT10)" /><div className="promo-discount-fields"><select name="discount_type" defaultValue="PERCENT"><option value="PERCENT">Percent</option><option value="FIXED">Fixed KZT</option></select><input name="discount_value" type="number" min="0.01" step="0.01" max="1000000" required placeholder="Discount value" /></div><label>Starts<input name="starts_at" type="datetime-local" required /></label><label>Ends<input name="ends_at" type="datetime-local" required /></label><input name="usage_limit" type="number" min="1" placeholder="Total uses (optional)" /><input name="per_user_limit" type="number" min="1" defaultValue="1" required placeholder="Uses per customer" /><button disabled={mutation.isPending}>Create code <ArrowRight size={14} /></button></form>}</div>
      <div className="role-table-wrap"><table className="role-table"><thead><tr><th>Code</th><th>Discount</th><th>Validity</th><th>Uses</th><th>State</th><th>Action</th></tr></thead><tbody>{promoCodes.map((promo) => <tr key={promo.id}><td><strong>{promo.code}</strong></td><td>{promo.discount_type === "PERCENT" ? `${promo.discount_value}%` : `${Number(promo.discount_value).toLocaleString("ru-RU")} KZT`}</td><td>{new Date(promo.starts_at).toLocaleDateString()}–{new Date(promo.ends_at).toLocaleDateString()}</td><td>{promo.used_count}{promo.usage_limit ? ` / ${promo.usage_limit}` : " / ∞"}</td><td>{promo.is_active ? "Active" : "Disabled"}</td><td><button className="table-action" disabled={mutation.isPending} onClick={() => mutation.mutate({ path: `/owner/promo-codes/${promo.id}`, method: "PATCH", body: { is_active: !promo.is_active } })}>{promo.is_active ? "Disable" : "Enable"}</button></td></tr>)}</tbody></table>{promoCodes.length === 0 && <p className="role-empty">No promo codes created yet.</p>}</div>
    </section>
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">MEMBERSHIPS</div><h2>Prepaid hour packs</h2></div><span>{membershipPlans.length} configured</span></div>
      {clubs.length > 0 && <form className="role-form membership-plan-form" onSubmit={createMembershipPlan}><h3>Create a membership pack</h3><select name="club_id" required defaultValue=""><option value="" disabled>Select a club</option>{clubOptions}</select><input name="name" required minLength={2} maxLength={80} placeholder="Package name" /><textarea name="description" maxLength={500} placeholder="Description" /><div className="promo-discount-fields"><input name="hours" type="number" min="1" max="1000" required placeholder="Included hours" /><input name="price" type="number" min="0.01" step="0.01" required placeholder="Price (KZT)" /><input name="validity_days" type="number" min="1" max="3650" defaultValue="30" required placeholder="Valid days" /></div><button disabled={mutation.isPending}>Create pack <ArrowRight size={14} /></button></form>}
      <div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club</th><th>Package</th><th>Hours</th><th>Price</th><th>Valid</th><th>State</th><th>Action</th></tr></thead><tbody>{membershipPlans.map((plan) => <tr key={plan.id}><td>{clubs.find((club) => club.id === plan.club_id)?.name ?? "Club"}</td><td><strong>{plan.name}</strong><small>{plan.description}</small></td><td>{plan.hours}</td><td>{Number(plan.price).toLocaleString("ru-RU")} KZT</td><td>{plan.validity_days} days</td><td>{plan.is_active ? "Active" : "Disabled"}</td><td><button className="table-action" disabled={mutation.isPending} onClick={() => mutation.mutate({ path: `/owner/membership-plans/${plan.id}`, method: "PATCH", body: { is_active: !plan.is_active } })}>{plan.is_active ? "Disable" : "Enable"}</button></td></tr>)}</tbody></table>{membershipPlans.length === 0 && <p className="role-empty">No membership packs created yet.</p>}</div>
    </section>
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">STAFF ROSTER</div><h2>Scheduled shifts</h2></div><span>{shifts.length} shown</span></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club</th><th>Staff</th><th>Starts</th><th>Ends</th><th>Action</th></tr></thead><tbody>{shifts.map((shift) => <tr key={shift.id}><td>{shift.club_name}</td><td>{shift.staff_name}<small>{shift.staff_email}</small></td><td>{new Date(shift.start_time).toLocaleString()}</td><td>{new Date(shift.end_time).toLocaleString()}</td><td><button className="table-action" disabled={mutation.isPending} onClick={() => mutation.mutate({ path: `/owner/shifts/${shift.id}`, method: "DELETE" })}>Cancel</button></td></tr>)}</tbody></table>{shifts.length === 0 && <p className="role-empty">No shifts scheduled yet.</p>}</div></section>
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">RESERVATIONS</div><h2>Recent bookings</h2></div><span>{bookings.length} shown</span></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club</th><th>Customer</th><th>Computer</th><th>Start</th><th>Status</th><th>Total</th></tr></thead><tbody>{bookings.slice(0, 30).map((booking) => <tr key={booking.id}><td>{booking.club_name}</td><td>{booking.customer_name}</td><td>{booking.computer_name}</td><td>{new Date(booking.start_time).toLocaleString()}</td><td>{booking.status}</td><td>{Number(booking.total_price).toLocaleString()} KZT</td></tr>)}</tbody></table>{bookings.length === 0 && <p className="role-empty">No bookings yet.</p>}</div></section>
    <AuditSection entries={audit} />
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
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">MY ROSTER</div><h2>Scheduled shifts</h2></div><span>{data.shifts.length} shown</span></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club</th><th>Shift starts</th><th>Shift ends</th></tr></thead><tbody>{data.shifts.map((shift) => <tr key={shift.id}><td>{shift.club_name}</td><td>{new Date(shift.start_time).toLocaleString()}</td><td>{new Date(shift.end_time).toLocaleString()}</td></tr>)}</tbody></table>{data.shifts.length === 0 && <p className="role-empty">No shifts are scheduled for your assigned clubs.</p>}</div></section>
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
  const { summary, users, clubs, bookings, audit } = query.data;
  return <>
    <StatStrip values={[{ label: "USERS", value: summary.users }, { label: "ACTIVE USERS", value: summary.active_users }, { label: "CLUBS", value: summary.active_clubs }, { label: "ACTIVE COMPUTERS", value: summary.active_computers }, { label: "TODAY’S BOOKINGS", value: summary.bookings_today }, { label: "TODAY’S REVENUE", value: `${Number(summary.revenue_today).toLocaleString()} KZT` }]} />
    {mutation.isError && <p className="role-error" role="alert">{mutation.error.message}</p>}{mutation.isSuccess && <p className="role-success" role="status">Platform record updated.</p>}
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">PLATFORM ACCESS</div><h2>Users</h2></div><span>{users.length} shown</span></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Name</th><th>Email</th><th>Username</th><th>Role</th><th>State</th><th>Action</th></tr></thead><tbody>{users.map((account) => <tr key={account.id}><td>{account.full_name}</td><td>{account.email}</td><td>{account.username}</td><td>{account.role}</td><td>{account.is_active ? "Active" : "Suspended"}</td><td>{account.id === profile.id ? "Current admin" : <button className="table-action" onClick={() => mutation.mutate({ path: `/admin/users/${account.id}/status`, body: { is_active: !account.is_active } })}>{account.is_active ? "Suspend" : "Reactivate"}</button>}</td></tr>)}</tbody></table></div></section>
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">VENUES</div><h2>Clubs</h2></div><span>{clubs.length} shown</span></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club</th><th>City</th><th>Owner ID</th><th>Stations</th><th>State</th><th>Action</th></tr></thead><tbody>{clubs.map((club) => <tr key={club.id}><td>{club.name}</td><td>{club.city}</td><td>{club.owner_id.slice(0, 8)}</td><td>{club.computers.length}</td><td>{club.is_active ? "Active" : "Paused"}</td><td><button className="table-action" onClick={() => mutation.mutate({ path: `/admin/clubs/${club.id}/status`, body: { is_active: !club.is_active } })}>{club.is_active ? "Pause" : "Activate"}</button></td></tr>)}</tbody></table></div></section>
    <section className="role-section"><div className="role-section-head"><div><div className="eyebrow">GLOBAL ACTIVITY</div><h2>Recent bookings</h2></div><span>{bookings.length} shown</span></div><div className="role-table-wrap"><table className="role-table"><thead><tr><th>Club</th><th>Customer</th><th>Computer</th><th>Start</th><th>Status</th><th>Total</th></tr></thead><tbody>{bookings.slice(0, 40).map((booking) => <tr key={booking.id}><td>{booking.club_name}</td><td>{booking.customer_name}</td><td>{booking.computer_name}</td><td>{new Date(booking.start_time).toLocaleString()}</td><td>{booking.status}</td><td>{Number(booking.total_price).toLocaleString()} KZT</td></tr>)}</tbody></table></div></section>
    <AuditSection entries={audit} />
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
