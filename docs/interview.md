# Putting this project on your CV

## A CV line

> **Travel fare intelligence dashboard.** Built a pipeline that scrapes flight search
> results from 4 travel sites daily (rate-limited, robots-aware), cleans ~800
> unstructured listings a day into a typed schema with an LLM (Claude, structured
> outputs, cached batches), validates every row and quarantines failures, models the
> data as a DuckDB star schema, and publishes a Power BI report with dynamic
> row-level security for regional teams. Measured cleaning accuracy field by field
> against ground truth: rules 76% of rows fully correct vs LLM __%.

Fill in the blank with your own `eval` run, and say which model. A number you measured
beats any adjective.

## The questions you will get, and what to say

**"Why an LLM? Why not just write parsers?"**
Run `eval` with the fake cleaner and show the table: the regex rules are perfect on the
three sites they were written for and fail completely on the fourth. Every new site
means new rules; the LLM reads a format it has never seen. Then say what you did about
the LLM's weaknesses: structured outputs, deterministic checks, a quarantine table,
and a cache so you never pay twice.

**"How do you know the LLM didn't make up a price?"**
The checks: the price must be in range, the offer must be below the price, the times
must fit the duration, the route and date must match the search that produced the
page. Failures are quarantined with a reason and shown on the data-quality page. And
`eval` measures accuracy against ground truth instead of trusting it.

**"What is row-level security and how did you do it?"**
One role, `Desk`, with a DAX filter on `dim_route`: the origin must be one of the
airports listed for `USERPRINCIPALNAME()` in a `user_access` table. Because `dim_route`
filters the fact table through a one-to-many relationship, every fact row is secured
by one rule. Adding a person is a row, not a new role. An unknown user sees nothing.
Mention the trap: RLS only applies to workspace Viewers; Admins, Members and
Contributors see everything.

**"Why a star schema?"**
Power BI's engine is built for it: filters flow from small dimensions to one big fact
table, DAX stays simple, and RLS on a dimension secures the fact. Show the model view.

**"What does the data say?"**
Have two findings ready from your own dashboard, for example: fares on a route roughly
double in the last five days before departure; one site is cheapest for the same
flight most of the time, by about 3-4%.

**"How would you run this every day?"**
A scheduled job (GitHub Actions, cron, or Azure Functions) runs scrape, clean, build,
export and publish; or put the export on SharePoint/Blob storage and use Power BI
scheduled refresh. Mention the cache: a daily run only pays for new listings.

**"Is scraping travel sites legal?"**
Say what you did: the fetcher obeys robots.txt and rate-limits itself, the demo runs on
fictional sites, and for real data you would read each site's terms and prefer an
official API or affiliate feed. Not knowing this is a red flag for an interviewer;
knowing it is a green one.

## Make it yours

Pick one and do it before you send the CV:

- Add hotels (`docs/extending.md`) and a "trip cost" page: flight plus two nights.
- Point the scraper at a source whose terms allow it, and show real numbers.
- Run `eval` on two Claude models and write a short note on cost versus accuracy.
- Add a price-drop alert: a scheduled job that emails when a tracked fare falls 15%.
