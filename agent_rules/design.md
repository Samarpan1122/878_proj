# Design

The current interface authority is now [DESIGN.md](../DESIGN.md), with the screening surface described in `.impeccable/surfaces/web-static-safety-html.md`. The notes below describe the original map/report phase only.

Research pipeline; the only UI is the folium map and matplotlib figures.

## Color and theme
- Basemap: CartoDB Positron (light, low-contrast so data layers read clearly).
- Severity / hotspot type (diverging, red = worse): frequent+severe `#b2182b`, infrequent but severe `#ef8a62`,
  frequent mostly minor `#67a9cf`, neither `#999999`.
- Outcome anomalies: purple `#762a83` (distinct from the severity ramp).
- Regimes: ColorBrewer Dark2 (categorical).

## Fonts / typography
Folium and matplotlib defaults. Figures saved at 120 dpi.
