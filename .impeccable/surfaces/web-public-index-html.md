---
version: 1
slug: "web-public-index-html"
primary_target: "web/public/index.html"
related_targets: ["web/public/app.css", "web/public/app.js", "web/public/SURFACE.md"]
---

# Public road safety observatory

Route: `/explore/`. The public `/` route is the separate 3D homepage documented in `web-public-home-html.md`.

Mode: Operate. Audience: transportation analysts and visitors evaluating GeoCrash. Scope: `web/public/index.html`, `app.css`, `app.js`, and the geographic boundary assets. The new public surface inherits the Cobalt Workbench; original private and research assets remain separate.

The visitor chooses a state and observation year, explores real FARS geographic aggregates, compares annual records, runs the deployed state-level count model, and inspects recorded factors and API evidence. A prominent Road screening link opens the existing real Nebraska screening engine.

The first viewport pairs a wide geographic plot with a compact state comparison rail. Shared filters drive summary, map, annual table and recorded-factor cohort together; state selection also preselects the forecast geography. The historical forecast requires an explicit Run forecast action. Below are model evidence, recorded factor counts with missingness, source register and API examples. No invented statistical values, live-incident claims or trained-foundation-model claims appear.

All API data are treated as untrusted text and rendered escaped. Visible dates, units, model limits, suppressed-cell coverage and reporting scope travel with the results. Filter failures retain the previous result with explicit error and recovery copy. The model and overall dataset can independently fail without inventing fallback values. Native controls, labeled focusable table scrollers, keyboard state selection and no ambient animation preserve usability.

The map uses local GeoJSON derived from the US Atlas 3 `states-10m.json` distribution of U.S. Census cartographic boundaries. No browser map tile, API key, CDN script or external font is required. The contiguous states use longitude/latitude scaling, with separately scaled Alaska and Hawaii insets. Selected states fit to their own geographic extent. Source: https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json . Conversion decodes delta arcs and preserves geometry; attribution/license is bundled as `US-ATLAS-LICENSE.txt` and linked in the website.

Direction contract: split geographic plot and state ranking (candidate 5; surface seed 6404e4b3). Cobalt actions, cool paper and ruled analytical sections retain the established visual identity. Desktop uses adjacent map and rankings; mobile stacks them, with locally scrolling tables. System fallbacks are intentional in this analytical Operate surface; no font loading is claimed.

Integrated browser checks passed at 1440px and 390px: 153,273 actual records; all 51 state boundaries; 3,023 pooled geographic cells; Nebraska 2024 cohort of 223 crashes; runtime forecast and metrics; recorded-factor categories; reset; error recovery; Alaska/Hawaii; no viewport overflow or JavaScript errors. Screenshots and executable browser checks live in `/tmp/geocrash-ui-check/public*`. The detector reported only documented-type-ramp advisories, with no blocking findings. Independent `public_finish` disposition is **SHIP**, with no material fixes. It additionally verified all 11 links, screening/inference/economics, 413/422 guards and research-route isolation. This brief does not imply external agency validation, traffic-volume normalization of the national explorer, or a production-qualified forecast.

Documentation merge: the implemented source brief above is preserved from `web/public/SURFACE.md`. The public surface extends root `DESIGN.md`; it does not replace private, research, or optional synthetic views. Cloud release and final finish disposition are tracked in `docs/PUBLIC_DEPLOYMENT.md`.

Final review evidence: `/tmp/geocrash-ui-check/public-review-{1440,390}.png` and `/tmp/geocrash-ui-check/public-screening-{1440,390}.png`.
