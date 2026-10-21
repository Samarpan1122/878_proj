---
version: 1
slug: "web-static-safety-html"
primary_target: "web/static/safety.html"
related_targets: ["web/static/safety.css","web/static/safety.js","web/static/safety-evidence.js"]
---

# Safety screening workspace

Mode: Operate. Surface: `web/static/safety.html`, with `safety.css`, `safety.js`, and `safety-evidence.js`.

The user requested exposure-normalized screening and countermeasure economics for a Nebraska study. Analysts choose Omaha, Lincoln or statewide coverage, compare fatal-crash screening signals, inspect one segment and its uncertainty, then explicitly confirm a treatment's applicability before calculating a scenario.

Extend the incumbent Cobalt workbench without redesigning the legacy explorer. Flush header, cool-paper surface, compact sortable table and adjacent segment inspection panel. On mobile the inspector follows the horizontally scrollable results table. Keep exposure-vintage limitations adjacent to the task; sources, licensing gaps and pipeline diagnostics remain accessible below it.

Evidence comes exclusively from the safety API. Official-source mode never substitutes fabricated rows or claims pilot success, commercial clearance or intervention effects. A separate explicit synthetic mode uses invented examples solely to demonstrate the workflow. Benefit calculations require a reviewed eligible share, explicit fatal-outcome transfer assumption and analyst-supplied costs. Agency partner and state data commercial reuse remain unresolved.

Validation: real local API at 1440px and 390px, area selection, sorting, segment inspection and scenario calculation. No viewport overflow or JavaScript errors. Temporary screenshots are in `/tmp/geocrash-ui-check/`.

Finish review disposition: **ship** for the implemented UI. The reviewed local snapshot displays the actual 2021–2024 FARS window, AADT 2025 as proxy exposure, and statewide linkage coverage of 650 / 835 fatal crashes (77.8%). Coverage is explicitly statewide, independent of the selected study area. These are review-time observations, not fixed design tokens or deployment claims.

The safety page locally darkens the shared cobalt accent to `oklch(54% .2 256)`; the finish review measured approximately 4.915:1 contrast against paper. The global Cobalt Workbench and implemented component vocabulary are documented in root `DESIGN.md`, with schema-v2 previews in `.impeccable/design.json`.

The implemented extension adds two ruled evidence sections below the scenario workflow. Model comparison exposes later-year and unseen-geography protocols, aligned metric columns, improvement intervals, and expandable methods with a complete reproducible report. Recorded behavior factors expose Nebraska/United States geography and available-year selectors, retain yes/no/unknown/not-applicable counts, and pair known-case shares with cobalt meters and available intervals. Both tables use labeled, focusable scroll regions; values come from `/api/safety/model-evidence` and `/api/safety/behavior`.

Existing primitives remain authoritative: analysis labels are 12px semibold with 6px spacing, tables are 13px with a 170px minimum first column, and cobalt meters are 8px high with a 90px minimum width. At 740px the section heading stacks, geography/year controls wrap, and table cells use 10px padding. Analysis tables have no maximum-height cap; their horizontal scroll contains the full dataset width.

The purpose is credible model and recorded-behavior analysis. A development comparison winner still requires independent validation; recorded factors describe fatal-crash findings rather than individual intent, causation, or risk among all road users. The extension makes no foundation-model claim.

Extension finish review: `advanced_finish_reviewer` disposition **ship**, with all requested fixes resolved. The reviewed desktop 1440px and mobile 390px surfaces had no viewport overflow or JavaScript errors. Cobalt meter fills were made explicit across browser meter implementations. Existing density, font-loading, and warm-notice prose detector observations remain advisory; they do not establish a new visual direction or claim of changed fonts.


Synthetic demonstration extension (2026-09-29): status metadata `data_mode=synthetic` changes the document title, main heading, area note, notice, coverage explanation and footer. It identifies 24 fictional corridors near Omaha and Lincoln and states that no model was trained for the demo. Model comparison, recorded-factor panels and their anchor links hide in this mode. The table, inspector, source register and guarded scenario form remain usable with explicit invented-data context. CSV names include `SYNTHETIC-demo`. Safety-only navigation hides unavailable explorer/research destinations and keeps the wordmark on the safety workspace.

This is a state/copy refinement using the existing warm-paper notice and Cobalt Workbench components; no visual identity or token changes. Synthetic numbers and intervals are never displayed as measured model performance. Independent synthetic finish review disposition: **SHIP** at 1440px and 390px. Banner, invented inspector/interval wording, scenario warning, synthetic CSV labeling, area reset and hidden research sections passed with no JavaScript errors or viewport overflow. Evidence: `/tmp/geocrash-ui-check/pilot-confirm-desktop.png` and `pilot-confirm-mobile.png`. This is interface verification, not commercial or model approval.
