# Provider certification

The `Provider certification` workflow checks Alpha Vantage, FRED, and ALFRED against live
provider responses every Tuesday at 06:23 UTC. The complete scheduled request set makes 16
Alpha Vantage requests and four FRED requests. Alpha Vantage requests use a smoothed 150-request
per-minute limiter. FRED requests remain below its two-request-per-second limit.

Scheduled workflows run from GitHub's default branch. The path-filtered `develop` push job only
validates the workflow and test configuration; it never receives provider secrets or makes live
requests. The weekly schedule becomes effective when a release carries the workflow to `main`.

## Protected credentials

Live jobs use the `provider-certification` GitHub environment. That environment accepts only
`develop` and `main`, and holds these environment secrets:

- `PERSISTRA_ALPHAVANTAGE_API_KEY`
- `PERSISTRA_FRED_API_KEY`

Set each secret through an interactive standard-input prompt so its value does not appear in the
shell command or history:

```bash
gh secret set PERSISTRA_ALPHAVANTAGE_API_KEY \
  --env provider-certification --repo fallblu/persistra
gh secret set PERSISTRA_FRED_API_KEY \
  --env provider-certification --repo fallblu/persistra
```

The workflow has read-only repository permission, disables persisted checkout credentials, and
does not upload artifacts. Provider cache files exist only in each job's temporary test directory.
Successful tests emit only their test names and outcomes. They do not log keys, raw responses,
schema details, observation values, or observation-derived fingerprints. Failures name the
operation, phase, and exception class without rendering the provider response.

## Entitlement boundaries

Alpha Vantage certification is divided into three sequential jobs:

1. Baseline families cover historical quotes, daily securities, currencies, commodities,
   economics, references, and the index catalog.
2. The premium-plan job covers historical options available on the confirmed 150-request-per-minute
   plan.
3. The market-data-entitlements job covers historical index data, realtime bulk quotes, and
   realtime top-of-book data. Alpha Vantage requires these US market-data entitlements to be
   activated separately through the **Data** page in Alpha X Terminal.

This separation makes an entitlement failure distinguishable from general authentication or
schema drift. A manual run can omit the third job while entitlement setup is incomplete:

```bash
gh workflow run provider-certification.yml --ref develop \
  -f market_data_entitlements=false
```

Scheduled runs always include all three scopes. Alpha Vantage documents premium functions and
market-data activation in its [API documentation](https://www.alphavantage.co/documentation/) and
[premium account guidance](https://www.alphavantage.co/premium/). FRED documents its request
limit in the [API error reference](https://fred.stlouisfed.org/docs/api/fred/errors.html).

## Investigate a failure

Start with the failed job and operation named in its log:

- `AuthenticationError` means the corresponding environment secret should be replaced.
- `EntitlementError` in the premium or market-data job means the account plan or Alpha X Data
  activation should be checked.
- `RateLimitError` means another consumer may be using the key or the provider changed its quota.
- `ResponseError` usually means a provider schema or value contract changed.
- `TransportError` may be transient; retry the workflow once before changing code.

Rerun manually after correcting credentials, entitlement, or a transient provider failure:

```bash
gh workflow run provider-certification.yml --ref develop \
  -f market_data_entitlements=true
```

For parser investigation, reproduce only the named live test in an authorized local environment.
Do not paste keys into command arguments, upload raw response caches, enable HTTP debug logging, or
copy licensed observations into an issue. Record the run URL, provider operation, exception class,
and any redacted schema diagnostic fields instead.
