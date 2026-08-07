# Analysis and visualization

Analysis functions will accept normalized data and explicit mathematical choices. They
will not fetch data. Plot functions will use Matplotlib and will accept caller-owned axes.

The general functions cover coverage and summary statistics, absolute and percentage
changes, simple and log returns, rebasing, cumulative returns, drawdowns, rolling statistics,
and covariance and correlation. They operate on ordinary wide numeric frames, so the same
tools apply to market, commodity, and economic observations after an explicit pivot or
alignment.

General analysis works on explicit wide numeric frames. Changes and returns do not fill or
bridge missing levels. Log functions require positive levels. Rolling functions require a
complete window by default. Annualized volatility requires a positive `periods_per_year`.
Sample standard deviations use `ddof=1`. Covariance and correlation use pairwise complete
observations.

Market analysis includes bid-ask spreads, bar and true ranges, volume summaries, realized
volatility, and observed session coverage. Economic analysis includes explicit-unit basis
point changes, lagged growth, and noninterpolated Treasury curves.

Historical option analysis supports contract filters, days to expiration, observed spreads,
chain summaries, implied-volatility preparation, and provider-supplied Greek profiles.
Moneyness uses spot divided by strike. Moneyness, intrinsic value, and time value require an
explicit positive underlying price. The functions do not price options, calculate Greeks, or
interpolate volatility surfaces.

All plots use Matplotlib. Functions return their axes and do not change global `rcParams`.
Heatmaps preserve missing cells and use no interpolation.

General plots include time series, distributions, coverage, rolling statistics, rebased
comparisons, and correlation matrices. Market plots include candlesticks and volume, returns,
cumulative returns, drawdowns, rolling volatility, and quote/spread history. Option plots
cover observed prices, volume/open interest, volatility smiles and surfaces, and supplied
Greek profiles. Economic plots cover scalar levels and changes plus yield curves and their
observed history.

The plotting layer expects calculations as inputs when a calculation has meaningful policy.
For example, calculate returns with `simple_returns` before calling `plot_returns`. This keeps
missing-value, lag, annualization, and unit choices visible in research code.
