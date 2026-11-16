// The four charts. Single-series charts use one colour (the title names the series);
// the stacked quality bar uses status colours, always with a text legend beside them.

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { LeadTimePoint, Quality, SiteScore, TrendPoint } from "../api/types";
import { number, percent, rupees, shortDay } from "../lib/format";

const AXIS = { stroke: "var(--text-muted)", fontSize: 12 };
const GRID = <CartesianGrid stroke="var(--grid)" vertical={false} />;

interface TipProps {
  active?: boolean;
  payload?: { payload?: Record<string, number | string> }[];
}

function Tip({ title, lines }: { title: string; lines: [string, string][] }) {
  return (
    <div className="tooltip">
      <div className="t-title">{title}</div>
      {lines.map(([k, v]) => (
        <div key={k}>
          {k}: <span className="t-value">{v}</span>
        </div>
      ))}
    </div>
  );
}

export function TrendChart({ points }: { points: TrendPoint[] }) {
  if (points.length < 2) return <p className="empty">Needs two or more scrape days for this departure.</p>;
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={points} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
        {GRID}
        <XAxis dataKey="scrape_date" tickFormatter={shortDay} tick={AXIS} stroke="var(--grid)" />
        <YAxis tickFormatter={(v: number) => rupees(v)} tick={AXIS} stroke="var(--grid)" width={72} />
        <Tooltip
          cursor={{ stroke: "var(--text-muted)", strokeDasharray: "3 3" }}
          content={({ active, payload }: TipProps) => {
            const p = payload?.[0]?.payload;
            if (!active || !p) return null;
            return (
              <Tip
                title={`Scraped ${shortDay(String(p.scrape_date))}`}
                lines={[
                  ["Cheapest", rupees(Number(p.cheapest_inr))],
                  ["Days to departure", String(p.days_to_departure)],
                ]}
              />
            );
          }}
        />
        <Line
          type="monotone"
          dataKey="cheapest_inr"
          stroke="var(--series-1)"
          strokeWidth={2}
          dot={{ r: 4, strokeWidth: 2, stroke: "var(--surface-1)", fill: "var(--series-1)" }}
          activeDot={{ r: 5, strokeWidth: 2, stroke: "var(--surface-1)" }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function LeadTimeChart({ points }: { points: LeadTimePoint[] }) {
  if (!points.length) return <p className="empty">No data for this route yet.</p>;
  // Far-out on the left, departure day on the right: read it like a countdown.
  const data = [...points].sort((a, b) => b.days_to_departure - a.days_to_departure);
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
        {GRID}
        <XAxis
          dataKey="days_to_departure"
          tick={AXIS}
          stroke="var(--grid)"
          tickFormatter={(d: number) => `${d}d`}
        />
        <YAxis tickFormatter={(v: number) => rupees(v)} tick={AXIS} stroke="var(--grid)" width={72} />
        <Tooltip
          cursor={{ stroke: "var(--text-muted)", strokeDasharray: "3 3" }}
          content={({ active, payload }: TipProps) => {
            const p = payload?.[0]?.payload;
            if (!active || !p) return null;
            return (
              <Tip
                title={`${p.days_to_departure} days before departure`}
                lines={[
                  ["Average cheapest", rupees(Number(p.avg_cheapest_inr))],
                  ["Samples", number(Number(p.samples))],
                ]}
              />
            );
          }}
        />
        <Line
          type="monotone"
          dataKey="avg_cheapest_inr"
          stroke="var(--series-1)"
          strokeWidth={2}
          dot={{ r: 4, strokeWidth: 2, stroke: "var(--surface-1)", fill: "var(--series-1)" }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function SiteChart({ sites }: { sites: SiteScore[] }) {
  if (!sites.length) return <p className="empty">No flight is priced on two sites yet.</p>;
  return (
    <ResponsiveContainer width="100%" height={44 * sites.length + 30}>
      <BarChart data={sites} layout="vertical" margin={{ top: 0, right: 40, left: 0, bottom: 0 }} barCategoryGap={8}>
        <CartesianGrid stroke="var(--grid)" horizontal={false} />
        <XAxis type="number" tickFormatter={(v: number) => `${v}%`} tick={AXIS} stroke="var(--grid)" />
        <YAxis type="category" dataKey="site_name" tick={AXIS} stroke="var(--grid)" width={96} />
        <Tooltip
          cursor={{ fill: "var(--accent-soft)" }}
          content={({ active, payload }: TipProps) => {
            const p = payload?.[0]?.payload;
            if (!active || !p) return null;
            return (
              <Tip
                title={String(p.site_name)}
                lines={[
                  ["Above the cheapest site", percent(Number(p.avg_premium_pct), 2)],
                  ["Cheapest of all", percent(Number(p.cheapest_pct))],
                  ["Quotes compared", number(Number(p.compared_quotes))],
                ]}
              />
            );
          }}
        />
        <Bar
          dataKey="avg_premium_pct"
          fill="var(--series-1)"
          radius={[0, 4, 4, 0]}
          isAnimationActive={false}
          label={{ position: "right", fill: "var(--text-secondary)", fontSize: 12, formatter: (v: number) => `${v.toFixed(1)}%` }}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

const QUALITY_PARTS = [
  { key: "ok", label: "Usable", color: "var(--status-good)" },
  { key: "ads", label: "Ads (expected)", color: "var(--status-neutral)" },
  { key: "rejected", label: "Rejected by checks", color: "var(--status-critical)" },
] as const;

export function QualityChart({ rows }: { rows: Quality["by_site"] }) {
  if (!rows.length) return <p className="empty">Nothing cleaned yet.</p>;
  return (
    <>
      <div className="legend">
        {QUALITY_PARTS.map((p) => (
          <span key={p.key}>
            <span className="swatch" style={{ background: p.color }} />
            {p.label}
          </span>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={44 * rows.length + 30}>
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 12, left: 0, bottom: 0 }} barCategoryGap={8}>
          <XAxis type="number" tick={AXIS} stroke="var(--grid)" tickFormatter={(v: number) => number(v)} />
          <YAxis type="category" dataKey="site_name" tick={AXIS} stroke="var(--grid)" width={96} />
          <Tooltip
            cursor={{ fill: "var(--accent-soft)" }}
            content={({ active, payload }: TipProps) => {
              const p = payload?.[0]?.payload;
              if (!active || !p) return null;
              return (
                <Tip
                  title={`${p.site_name}: ${percent(Number(p.ok_pct))} usable`}
                  lines={QUALITY_PARTS.map((q) => [q.label, number(Number(p[q.key]))])}
                />
              );
            }}
          />
          {QUALITY_PARTS.map((p, i) => (
            <Bar
              key={p.key}
              dataKey={p.key}
              stackId="q"
              fill={p.color}
              stroke="var(--surface-1)"
              strokeWidth={2}
              radius={i === QUALITY_PARTS.length - 1 ? [0, 4, 4, 0] : 0}
              isAnimationActive={false}
            >
              {rows.map((r) => (
                <Cell key={r.site_key} />
              ))}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </>
  );
}
