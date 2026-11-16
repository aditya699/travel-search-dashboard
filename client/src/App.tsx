import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { api, ApiError } from "./api/client";
import { LeadTimeChart, QualityChart, SiteChart, TrendChart } from "./components/charts";
import { day, number, percent, rupees, shortDay } from "./lib/format";

export default function App() {
  const users = useQuery({ queryKey: ["users"], queryFn: api.users });
  const [email, setEmail] = useState<string>("");
  useEffect(() => {
    if (!email && users.data?.[0]) setEmail(users.data[0].email);
  }, [email, users.data]);
  const viewer = users.data?.find((u) => u.email === email);

  if (users.error) return <Problem error={users.error} />;
  return (
    <div className="shell">
      <header className="top">
        <div>
          <h1>Travel Search Dashboard</h1>
          <div className="sub">Flight fares scraped from four travel sites, cleaned by an LLM, checked, modelled.</div>
        </div>
        <div className="controls">
          <label className="field">
            Viewing as (row-level security)
            <select value={email} onChange={(e) => setEmail(e.target.value)}>
              {users.data?.map((u) => (
                <option key={u.email} value={u.email}>
                  {u.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>
      {viewer && (
        <p className="hint">
          {viewer.email} sees routes from
          {viewer.origins.map((o) => (
            <span key={o} className="chip">
              {o === "*" ? "every airport" : o}
            </span>
          ))}
        </p>
      )}
      {email && <Dashboard key={email} email={email} />}
      <footer>
        Demo data from fictional sites and airlines. Same rules as the Power BI report: user_access.json →
        user_access table.
      </footer>
    </div>
  );
}

function Dashboard({ email }: { email: string }) {
  const routes = useQuery({ queryKey: ["routes", email], queryFn: () => api.routes(email) });
  const summary = useQuery({ queryKey: ["summary", email], queryFn: () => api.summary(email) });
  const sites = useQuery({ queryKey: ["sites", email], queryFn: () => api.sites(email) });
  const quality = useQuery({ queryKey: ["quality", email], queryFn: () => api.quality(email) });
  const [route, setRoute] = useState<string>("");
  useEffect(() => {
    if (!route && routes.data?.[0]) setRoute(routes.data[0].route_key);
  }, [route, routes.data]);

  const error = routes.error ?? summary.error;
  if (error) return <Problem error={error} />;
  const s = summary.data;
  const q = s?.quality;
  return (
    <>
      <section className="kpis">
        <Kpi
          label="Cheapest fare in the latest scrape"
          value={rupees(s?.cheapest?.cheapest_inr)}
          note={s?.cheapest ? `${s.cheapest.route_key} on ${day(s.cheapest.depart_date)} · ${s.cheapest.flight_number} · ${s.cheapest.site_key}` : ""}
        />
        <Kpi label="Average fare" value={rupees(s?.avg_fare_inr)} note={`${number(s?.quotes)} quotes, ${s?.routes ?? "-"} routes`} />
        <Kpi
          label="Scrape history"
          value={`${s?.scrape_days ?? "-"} days`}
          note={s?.first_scrape ? `${shortDay(s.first_scrape)} to ${shortDay(s.latest_scrape ?? s.first_scrape)}` : ""}
        />
        <Kpi
          label="Usable listings"
          value={q ? percent((100 * q.ok) / Math.max(q.listings, 1)) : "-"}
          note={q ? `${number(q.rejected)} rejected, ${number(q.ads)} ads` : ""}
        />
      </section>

      <div className="controls" style={{ marginBottom: 12 }}>
        <label className="field">
          Route
          <select value={route} onChange={(e) => setRoute(e.target.value)}>
            {routes.data?.map((r) => (
              <option key={r.route_key} value={r.route_key}>
                {r.route_label} ({r.route_key})
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid">
        {route && <RouteCards email={email} route={route} />}
        <section className="card">
          <h2>Which site is cheaper for the same flight</h2>
          <p className="hint">Average premium over the cheapest site, same flight, same day. Lower is better.</p>
          <SiteChart sites={sites.data ?? []} />
        </section>
        <section className="card">
          <h2>Data quality by site</h2>
          <p className="hint">Every scraped listing: usable, an ad, or rejected by the checks (and why).</p>
          <QualityChart rows={quality.data?.by_site ?? []} />
          {!!quality.data?.top_reasons.length && (
            <ul className="reasons">
              {quality.data.top_reasons.slice(0, 5).map((r) => (
                <li key={r.site_key + r.reason}>
                  <span>
                    {r.site_key}: {r.reason}
                  </span>
                  <span>{number(r.listings)}</span>
                </li>
              ))}
            </ul>
          )}
          {quality.data?.samples[0] && <div className="sample">{quality.data.samples[0].card_text}</div>}
        </section>
      </div>
    </>
  );
}

function RouteCards({ email, route }: { email: string; route: string }) {
  const cheapest = useQuery({ queryKey: ["cheapest", email, route], queryFn: () => api.cheapest(email, route) });
  const trend = useQuery({ queryKey: ["trend", email, route], queryFn: () => api.trend(email, route) });
  const lead = useQuery({ queryKey: ["lead", email, route], queryFn: () => api.leadTime(email, route) });

  // Departures seen in more than one scrape are the ones with a trend to show.
  const { departures, mostTracked } = useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of trend.data ?? []) counts.set(p.depart_date, (counts.get(p.depart_date) ?? 0) + 1);
    const tracked = [...counts].filter(([, n]) => n >= 2);
    const best = [...tracked].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] ?? "";
    return { departures: tracked.map(([d]) => d).sort(), mostTracked: best };
  }, [trend.data]);
  const [depart, setDepart] = useState("");
  // Open on the departure seen in the most scrapes: the longest line to read.
  const chosen = departures.includes(depart) ? depart : mostTracked;
  const points = (trend.data ?? []).filter((p) => p.depart_date === chosen);

  return (
    <>
      <section className="card wide">
        <h2>Cheapest option per departure date</h2>
        <p className="hint">From the latest scrape, across every site.</p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Departure</th>
                <th className="num">Days left</th>
                <th className="num">Cheapest</th>
                <th>Flight</th>
                <th>Departs</th>
                <th>Where</th>
                <th className="num">Options</th>
              </tr>
            </thead>
            <tbody>
              {cheapest.data?.map((c) => (
                <tr key={c.depart_date}>
                  <td>{day(c.depart_date)}</td>
                  <td className="num">{c.days_to_departure}</td>
                  <td className="num">
                    <strong>{rupees(c.cheapest_inr)}</strong>
                  </td>
                  <td>
                    {c.carrier_name} {c.flight_number}
                  </td>
                  <td>{c.depart_time}</td>
                  <td>{c.site_name}</td>
                  <td className="num">{c.options}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="card">
        <div className="card-head">
          <div>
            <h2>How the cheapest fare moved</h2>
            <p className="hint">One departure, tracked across scrape days.</p>
          </div>
          {departures.length > 0 && (
            <select value={chosen} onChange={(e) => setDepart(e.target.value)} aria-label="Departure date" style={{ minWidth: 140 }}>
              {departures.map((d) => (
                <option key={d} value={d}>
                  {day(d)}
                </option>
              ))}
            </select>
          )}
        </div>
        <TrendChart points={points} />
      </section>
      <section className="card">
        <h2>When to book</h2>
        <p className="hint">Average cheapest fare by days left before departure.</p>
        <LeadTimeChart points={lead.data ?? []} />
      </section>
    </>
  );
}

function Kpi({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      <div className="note">{note}</div>
    </div>
  );
}

function Problem({ error }: { error: unknown }) {
  const message = error instanceof ApiError || error instanceof Error ? error.message : String(error);
  return (
    <div className="shell">
      <div className="banner">
        <strong>Could not load the dashboard.</strong> {message}
      </div>
    </div>
  );
}
