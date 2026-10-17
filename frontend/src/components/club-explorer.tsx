"use client";

import Link from "next/link";
import Image from "next/image";
import { useDeferredValue, useState, useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowRight, ChevronDown, CircleHelp, Cpu, Gamepad2, MapPin, Search, ShieldCheck, Sparkles, Wifi, CircleUserRound } from "lucide-react";
import { getClubs } from "@/lib/api";
import { hasAccessToken, subscribeToAuth } from "@/lib/auth-session";

const cityOptions = ["All cities", "Almaty", "Astana", "Karaganda", "Pavlodar", "Shymkent"];
const images = [
  "https://images.unsplash.com/photo-1593305841991-05c297ba4575?auto=format&fit=crop&w=1000&q=85",
  "https://images.unsplash.com/photo-1542751371-adc38448a05e?auto=format&fit=crop&w=1000&q=85",
  "https://images.unsplash.com/photo-1598550476439-6847785fcea6?auto=format&fit=crop&w=1000&q=85",
  "https://images.unsplash.com/photo-1597872200969-2b65d56bd16b?auto=format&fit=crop&w=1000&q=85",
  "https://images.unsplash.com/photo-1603481546238-487240415921?auto=format&fit=crop&w=1000&q=85",
];

export function ClubExplorer() {
  const [search, setSearch] = useState("");
  const [city, setCity] = useState("");
  const authenticated = useSyncExternalStore(subscribeToAuth, hasAccessToken, () => false);
  const deferredSearch = useDeferredValue(search);
  const clubsQuery = useQuery({ queryKey: ["clubs", deferredSearch, city], queryFn: () => getClubs(deferredSearch, city) });
  const clubs = clubsQuery.data?.items ?? [];

  return (
    <main className="site-shell">
      <header className="topbar">
        <Link className="brand" href="/" aria-label="CyberBook home"><span className="brand-mark"><Gamepad2 size={19} /></span><span>cyber<span>book</span></span></Link>
        <nav className="main-nav" aria-label="Main navigation"><a className="nav-active" href="#clubs">Explore clubs</a><a href="#how-it-works">How it works</a></nav>
        <div className="account-nav">{authenticated ? <Link href="/profile" className="profile-link" aria-label="Profile" title="Profile"><CircleUserRound size={22} /></Link> : <><Link href="/login" className="sign-in">Sign in</Link><Link href="/register" className="join-button">Create account <ArrowRight size={15} /></Link></>}</div>
      </header>

      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <div className="eyebrow"><span className="live-dot" /> YOUR NEXT SESSION STARTS HERE</div>
          <h1 id="hero-title">Find your<br /><em>next level.</em></h1>
          <p>Compare gaming setups, check real club details, and book a seat that fits the way you play.</p>
          <a className="hero-link" href="#clubs">Explore nearby clubs <ArrowDownRight size={17} /></a>
          <div className="hero-proof"><span className="proof-icon"><ShieldCheck size={16} /></span><span>Live club listings</span><span className="proof-separator">/</span><span>Verified PC specs</span></div>
        </div>
        <div className="hero-visual">
          <Image src={images[0]} alt="Gaming PC setup inside a computer club" fill priority sizes="(max-width: 720px) 100vw, 55vw" />
          <div className="image-shade" />
          <div className="visual-label"><span className="visual-index">01</span><span>THE ARENA<br /><small>Find your setup</small></span><ArrowDownRight size={19} /></div>
          <div className="visual-stamp"><Sparkles size={15} /><span>PLAY<br />YOUR<br />WAY</span></div>
          <div className="visual-caption"><Wifi size={14} /> AVAILABLE SESSIONS UPDATED LIVE</div>
        </div>
        <div className="hero-side-note">CYBERBOOK / 01 — DISCOVER</div>
      </section>

      <section className="discovery" id="clubs" aria-labelledby="clubs-title">
        <div className="section-heading"><div><div className="eyebrow section-kicker">THE LINEUP <span>({clubsQuery.data?.total ?? "--"})</span></div><h2 id="clubs-title">Clubs worth your queue.</h2></div><p>Real hardware. Real locations.<br />Pick a place and make it yours.</p></div>
        <div className="filters" role="search">
          <label className="search-field"><Search size={18} /><span className="sr-only">Search clubs or hardware</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search club, city, or GPU" /></label>
          <label className="city-field"><MapPin size={17} /><span className="sr-only">Filter by city</span><select value={city} onChange={(event) => setCity(event.target.value)}>{cityOptions.map((option) => <option key={option} value={option === "All cities" ? "" : option}>{option}</option>)}</select><ChevronDown className="select-chevron" size={15} /></label>
          <div className="filter-hint"><span className="filter-key">TIP</span> Try RTX 4070</div>
        </div>
        {clubsQuery.isPending && <div className="result-state" role="status"><div className="loading-line" /><span>Finding clubs for you...</span></div>}
        {clubsQuery.isError && <div className="result-state error-state" role="alert"><CircleHelp size={20} /><div><strong>Club listings are unavailable.</strong><span>{clubsQuery.error.message}</span></div><button onClick={() => void clubsQuery.refetch()}>Try again</button></div>}
        {clubsQuery.isSuccess && clubs.length === 0 && <div className="result-state"><Search size={20} /><div><strong>No clubs match those filters.</strong><span>Try a different city or search term.</span></div></div>}
        {clubsQuery.isSuccess && clubs.length > 0 && <div className="club-grid">
          {clubs.map((club, index) => {
            const availableCount = club.computers.filter((computer) => computer.is_active && computer.status === "AVAILABLE").length;
            const minPrice = club.tariffs.reduce<number | null>((lowest, tariff) => {
              const value = Number(tariff.price_per_hour);
              return lowest === null || value < lowest ? value : lowest;
            }, null);
            const featuredComputer = club.computers.find((computer) => computer.is_active);
            return <article className="club-card" key={club.id}>
              <Link className="club-image" href={`/clubs/${club.id}`} aria-label={`View ${club.name}`}><Image src={images[(index + 1) % images.length]} alt={`${club.name} gaming area`} fill sizes="(max-width: 720px) 100vw, (max-width: 1050px) 50vw, 33vw" /><span className="city-chip"><MapPin size={12} />{club.city}</span><span className="card-number">0{index + 1}</span></Link>
              <div className="club-card-content">
                <div className="club-title-row"><div><h3>{club.name}</h3><p className="club-address">{club.address}</p></div><div className="rating"><span>★</span> {Number(club.rating).toFixed(1)}</div></div>
                <p className="club-description">{club.description}</p>
                <div className="spec-line"><Cpu size={14} /><span>{featuredComputer?.gpu ?? "PC specs coming soon"}</span><span className="spec-divider">·</span><span>{featuredComputer ? `${featuredComputer.ram_gb} GB` : ""}</span></div>
                <div className="card-footer"><span className="availability"><i />{availableCount} rigs available</span><span className="price">{minPrice === null ? "Ask at club" : <>{minPrice.toLocaleString("en-US")} <small>KZT / HR</small></>}</span></div>
                <Link className="card-action" href={`/clubs/${club.id}`}>View club <ArrowRight size={15} /></Link>
              </div>
            </article>;
          })}
        </div>}
      </section>

      <section className="how-strip" id="how-it-works"><div className="how-number">01 / 03</div><div><div className="eyebrow">NO GUESSWORK</div><h2>Good sessions<br />start with a plan.</h2></div><div className="how-step"><span>01</span><strong>Pick your club</strong><p>Compare locations and real PC setups.</p></div><div className="how-step"><span>02</span><strong>Choose a time</strong><p>See your price before you confirm.</p></div><div className="how-step"><span>03</span><strong>Show up and play</strong><p>Your booking details stay in one place.</p></div></section>
      <footer className="footer"><Link className="brand" href="/"><span className="brand-mark"><Gamepad2 size={17} /></span><span>cyber<span>book</span></span></Link><span>MAKE TIME FOR ONE MORE.</span><span>© 2026 CYBERBOOK</span></footer>
    </main>
  );
}