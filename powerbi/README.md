# Power BI: build, secure and publish the report

The pipeline ends in `server/data/powerbi/`: one Parquet (and CSV) file per table of a
star schema. This guide turns that into a published Power BI report where each person
sees only their own routes.

The files in this folder:

| File | What it is |
| --- | --- |
| [`load_tables.pq`](load_tables.pq) | Power Query (M) to load every table from the export folder |
| [`measures.dax`](measures.dax) | The report's measures, plus the relationships they expect |
| [`rls.dax`](rls.dax) | The dynamic row-level security role |
| [`theme.json`](theme.json) | A report theme with a colour-blind-safe palette |

You build the `.pbix` yourself in Power BI Desktop. It is not in the repo because it
embeds a data snapshot, and building it is the part of the project you will be asked
about.

## What you need

- **Power BI Desktop** (free, Windows; Microsoft Store or the Power BI download page).
- **To publish and share**: a work or school account with a Power BI Pro or Premium Per
  User licence, or a Fabric trial. A personal Gmail account cannot sign in to Power BI.
- **For RLS to mean anything**: a shared workspace (not *My workspace*), and the people
  you test with added as **Viewers** (see the warning in step 7).

## 1. Produce the data

```bash
cd server
uv run python -m app.cli demo
```

The export lands in `server/data/powerbi/`. Re-run `demo` (or `scrape`, `clean`,
`build`, `export`) whenever you want fresh numbers.

## 2. Load the tables

1. Open Power BI Desktop → **Blank report**.
2. **Home → Transform data → Manage parameters → New parameter**: name `DataFolder`,
   type *Text*, value = the full path of `server\data\powerbi\` **with a trailing
   backslash**.
3. For each block in `load_tables.pq`: **New source → Blank query → Advanced editor**,
   paste, and rename the query to the name in the comment (`fact_fare_quote`,
   `quarantine`, `dim_route`, `dim_site`, `dim_carrier`, `dim_airport`, `dim_date`,
   `user_access`).
4. **Close & Apply**.

## 3. Model

In **Model view**:

1. Create the relationships listed at the top of `measures.dax`. All are many-to-one,
   single direction. Make `fact_fare_quote[depart_date] → dim_date[date]` active and
   `fact_fare_quote[scrape_date] → dim_date[date]` inactive (the scrape-date measure
   switches to it with `USERELATIONSHIP`).
2. Select `dim_date` → **Mark as date table** → column `date`.
3. Sort `dim_date[month_name]` by `month` and `dim_date[weekday_name]` by
   `weekday_number` (**Column tools → Sort by column**).
4. Hide the key columns (`route_key`, `site_key`, `carrier_code`, `quote_id`) and the
   whole `user_access` table from report view. People should never drag them into a visual.

## 4. Measures

**Home → Enter data** → name the table `_Measures` → **Load**. Then add each measure in
`measures.dax` with **New measure**. Set `Cheapest Fare`, `Average Fare` and
`Cheapest Fare Today` to currency format, ₹ (*Format → Currency → ₹ English (India)*).

## 5. Report pages

**View → Themes → Browse for themes** → `theme.json`. A layout that works:

| Page | Visuals |
| --- | --- |
| **Overview** | Cards: `Cheapest Fare Today`, `Average Fare`, `Quotes`, `Usable Listing %`. Slicers: `dim_route[route_label]`, `dim_date[date]`. Table: departure date, carrier, flight, `Cheapest Fare`, site. |
| **Price trend** | Line chart: `dim_date[date]` on the axis with `Cheapest Fare by Scrape Date`, filtered to one departure date with a slicer on `fact_fare_quote[depart_date]`. |
| **When to book** | Line chart: `fact_fare_quote[days_to_departure]` (axis sorted descending) by `Avg Daily Cheapest`. |
| **Sites** | Bar chart: `dim_site[site_name]` by `Avg Premium vs Cheapest Site %`. |
| **Data quality** | Stacked bar: `dim_site[site_name]` by `Quotes`, `Ad Listings`, `Quarantined Listings`. Table of `quarantine[reasons]` and `quarantine[card_text]`. |

The web preview (`client/`) shows the same five views, so you can compare your work
against it.

## 6. Row-level security

1. **Modeling → Manage roles → New**, name it **`Desk`**.
2. Add the two table filters in `rls.dax` (one on `dim_route`, one on `user_access`). Save.
3. Test in Desktop: **Modeling → View as → Other user** = `delhi.desk@travel.example`,
   tick **Desk** → only routes from DEL remain. Try `head.analytics@travel.example`
   (everything) and a made-up email (nothing at all, which is what you want).
4. Save the file as `powerbi/TravelSearch.pbix`.

The demo emails are on `travel.example`, which cannot exist. For a real test, edit
`server/app/config/user_access.json` to use real colleagues' sign-in emails, re-run
`build` and `export`, and refresh in Desktop.

## 7. Publish

**Either** press **Publish** in Desktop and pick your workspace, **or** use the script:

```bash
cd server
uv run python -m app.cli publish
```

The script uploads the `.pbix` with the Power BI REST API (`CreateOrOverwrite`, so a
re-publish replaces the model instead of making a copy), waits for the import, prints
the report URL, and checks the RLS roles came with it. Setup, once:

1. **Entra admin center → App registrations → New registration**, single tenant.
2. **Authentication → Allow public client flows → Yes** (for device sign-in).
3. **API permissions → Add → Power BI Service → Delegated →
   `Dataset.ReadWrite.All`**, and grant consent if your tenant asks.
4. In `server/.env`: `PBI_CLIENT_ID` (the app's id), `PBI_TENANT_ID` (your tenant id or
   domain), `PBI_WORKSPACE_ID` (the GUID in `app.powerbi.com/groups/<id>/...`).

For unattended runs (a nightly GitHub Action), use `PBI_AUTH=service_principal` with a
client secret. A Power BI admin must allow service principals to use Power BI APIs in
the tenant settings, and the app must be a Member of the workspace.

Then assign people to the role. The REST API cannot do this step:

**Workspace → the semantic model → ⋯ → Security → Desk → add the people** (the same
emails as `user_access.json`, or a security group containing them).

> **RLS only applies to Viewers.** Workspace Admins, Members and Contributors can edit
> the model, so Power BI shows them every row whatever the roles say. Test with someone
> who has the Viewer role, or share the report or an app with them.
> **Test as role** in the service evaluates `USERPRINCIPALNAME()` as *you*, so it cannot
> fully stand in for another person; signing in as them is the real test.

## 8. Keeping it fresh

The published model holds the snapshot from when you last refreshed in Desktop. Two
ways to update it:

- **Re-publish** (simplest): run the pipeline, refresh in Desktop, `publish` again. A
  scheduled GitHub Action can do the pipeline and publish steps every night.
- **Scheduled refresh in the service**: move the export folder somewhere the service
  can reach (SharePoint/OneDrive, Azure Blob, or a Postgres database) and point the
  queries there. A folder on your laptop needs an on-premises data gateway instead.

These steps follow Microsoft's documentation as of November 2026. Menu names in Power
BI change now and then; if a menu has moved, search for the feature's name in the docs.
