---
version: 1
slug: "web-public-home-html"
primary_target: "web/public/home.html"
related_targets: ["web/public/home.css", "web/public/home.js"]
---

# Public 3D geographic homepage

Mode: Experience. Restore the original local explorer’s visual experience at the public `/` route, using permitted historical FARS aggregates. The analytical Cobalt Workbench remains at `/explore/`, and the road screening engine remains at `/screening/`. This is a geographic entry point into the working product, not a new model-performance claim.

Implementation sources are `web/public/home.html`, `home.css`, and `home.js`. The source uses a full-viewport dark map, a light floating filter bar, lower-left “See the road ahead.” introduction and city presets, and an upper-right evidence panel. Actions lead to road screening, the data workbench, its model section and API documentation. The bundled deck.gl 9.1.14 build and license are local, as are the 51 state boundaries; there are no remote map tiles, font downloads or runtime CDN scripts.

The map combines a selectable state-boundary GeoJSON layer with extruded hexagonal columns for the API’s 0.25-degree cells. Heights are `sqrt(fatal_crashes) × 4400` display units; taller columns mean more crashes, not a linear height scale or physical object height. Column colors vary monotonically with counts. Neither height nor color is severity or traffic-adjusted risk. Sparse cells are suppressed separately by state/year before pooling. Selected geography summaries retain complete fatal-crash/fatality totals, visible-cell count, suppression and missing-coordinate accounting.

Native state/year selectors provide keyboard access to geography. Omaha, Chicago, Dallas, New York and Los Angeles presets move the camera while retaining explicitly labeled state-level results. A clicked cell shows counts and its aggregate center, not a street-level crash location. Camera controls support zoom, 3D/flat, and reset view; Back to United States also resets filters. User-triggered flights take 1100ms or zero under reduced motion; there is no ambient rotation.

Observed tokens: dark canvas `#101722`, overlay paper `#f4f6fa`, overlay ink `#172335`, muted labels `#607085`, cobalt `#255cf2`, and rules `#d8dfe9`. Filters and summaries use 9px corners and existing map-overlay shadows. Headline is 48–76px desktop, 49px mobile, 40px short mobile. At 760px, the header wraps and a selected-state/cell evidence panel replaces the lower hero. At 1100px, the summary narrows from 277px to 255px. Native controls and links keep a 3px pale-blue focus outline with 4px offset. Space Grotesk/Inter are declared with system fallbacks; no font loading is claimed.

Graphics failures display a retry action and direct data-explorer fallback. Data-update failures retain the prior evidence and say so. A keyboard skip link opens the table-based workbench; the no-script message links to API documentation and real summary JSON. No screenshot or synthetic fallback replaces failed real data.

Independent `home_finish_reviewer` disposition: **SHIP**, with no outstanding material issues. Root checks passed at desktop 1440px and mobile 390px with actual WebGL: 153,273 records, Nebraska 2024 count 223, tilt/reset, Alaska/Hawaii, API-error recovery and unavailable-WebGL fallback. Mobile joined-word spacing was corrected after screenshot inspection. Nineteen API tests and the complete local public smoke check passed. The 3D homepage is serving on public Cloud Run revision `geocrash-00002-vkd` at 100% traffic. Anonymous smoke verification passed in `outputs/releases/public-3d-verification.json`, including state/road inference, economics, input guards and research isolation. Desktop/mobile cloud WebGL flows and fallback passed in `outputs/releases/public-3d-cloud-browser.json`, and the `/explore/` workbench regression passed. Models and data hashes are unchanged. The first post-rollout road-inference request timed out before a full retry passed; no cold-start SLA is claimed.
