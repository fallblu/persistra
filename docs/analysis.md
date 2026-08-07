# Analysis and visualization

Analysis functions will accept normalized data and explicit mathematical choices. They
will not fetch data. Plot functions will use Matplotlib and will accept caller-owned axes.

Historical option analysis supports contract filters, days to expiration, observed spreads,
chain summaries, implied-volatility preparation, and provider-supplied Greek profiles.
Moneyness, intrinsic value, and time value require an explicit positive underlying price.
The functions do not price options, calculate Greeks, or interpolate volatility surfaces.
