# Analysis and visualization

Analysis functions will accept normalized data and explicit mathematical choices. They
will not fetch data. Plot functions will use Matplotlib and will accept caller-owned axes.

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
