// Response shapes of the FastAPI server (server/app/api/queries.py).

export interface User {
  email: string;
  name: string;
  origins: string[];
}

export interface Route {
  route_key: string;
  origin: string;
  destination: string;
  route_label: string;
  distance_km: number;
}

export interface Summary {
  latest_scrape: string | null;
  first_scrape: string | null;
  scrape_days: number;
  quotes: number;
  routes: number;
  avg_fare_inr: number | null;
  cheapest: {
    route_key: string;
    depart_date: string;
    cheapest_inr: number;
    carrier_code: string;
    flight_number: string;
    site_key: string;
  } | null;
  quality: { listings: number; ok: number; ads: number; rejected: number };
}

export interface CheapestFare {
  route_key: string;
  route_label: string;
  depart_date: string;
  days_to_departure: number;
  cheapest_inr: number;
  carrier_code: string;
  carrier_name: string;
  flight_number: string;
  depart_time: string;
  site_key: string;
  site_name: string;
  options: number;
}

export interface TrendPoint {
  depart_date: string;
  scrape_date: string;
  days_to_departure: number;
  cheapest_inr: number;
}

export interface LeadTimePoint {
  days_to_departure: number;
  avg_cheapest_inr: number;
  samples: number;
}

export interface SiteScore {
  site_key: string;
  site_name: string;
  compared_quotes: number;
  cheapest_pct: number;
  avg_premium_pct: number;
}

export interface Quality {
  by_site: {
    site_key: string;
    site_name: string;
    listings: number;
    ok: number;
    ads: number;
    rejected: number;
    ok_pct: number;
  }[];
  top_reasons: { site_key: string; reason: string; listings: number }[];
  samples: { site_key: string; reasons: string; card_text: string }[];
}
