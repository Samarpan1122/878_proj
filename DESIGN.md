---
name: GeoCrash — Cobalt Workbench
description: Cool paper, cobalt actions, and precise ruled surfaces for road evidence.
colors:
  paper: "oklch(98.5% 0.004 250)"
  paper-2: "oklch(96.2% 0.006 250)"
  ink: "oklch(24% 0.02 258)"
  ink-2: "oklch(38% 0.018 257)"
  muted: "oklch(54% 0.014 257)"
  rule: "oklch(90.5% 0.008 255)"
  rule-strong: "oklch(82% 0.01 255)"
  accent: "oklch(58% 0.2 256)"
  safety-accent: "oklch(54% .2 256)"
  public-muted: "oklch(46% .014 257)"
  public-rule-strong: "oklch(76% .01 255)"
  public-risk: "oklch(45% .17 27)"
  home-paper: "#f4f6fa"
  home-ink: "#172335"
  home-muted: "#607085"
  home-cobalt: "#255cf2"
  home-line: "#d8dfe9"
  home-dark: "#101722"
  accent-soft: "oklch(93% 0.035 256)"
  accent-ink: "oklch(98.5% 0.004 250)"
  focus: "oklch(58% 0.2 256)"
  graphite: "oklch(22% 0.016 260)"
  graphite-ink: "oklch(92% 0.008 255)"
  risk: "oklch(53% 0.19 27)"
  safe: "oklch(55% 0.12 160)"
typography:
  display:
    fontFamily: '"Space Grotesk", ui-sans-serif, system-ui, sans-serif'
    fontSize: "2rem"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.025em"
  body:
    fontFamily: '"Inter", ui-sans-serif, system-ui, sans-serif'
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: '"JetBrains Mono", ui-monospace, monospace'
    fontSize: "0.6875rem"
    fontWeight: 500
    letterSpacing: "0.06em"
  safety-headline:
    fontFamily: '"Space Grotesk", ui-sans-serif, system-ui, sans-serif'
    fontSize: "30px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.03em"
  safety-title:
    fontFamily: '"Space Grotesk", ui-sans-serif, system-ui, sans-serif'
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.2
  safety-body:
    fontFamily: '"Inter", ui-sans-serif, system-ui, sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.55
rounded:
  sm: "4px"
  md: "6px"
  lg: "10px"
spacing:
  2xs: "0.25rem"
  xs: "0.5rem"
  sm: "0.75rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "2rem"
  2xl: "3rem"
components:
  safety-button-primary:
    backgroundColor: "{colors.safety-accent}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  safety-button-primary-hover:
    backgroundColor: "{colors.ink-2}"
    textColor: "{colors.paper}"
  safety-button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  safety-input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  safety-navigation:
    textColor: "{colors.ink-2}"
    padding: "20px 0"
  safety-status-tag:
    backgroundColor: "{colors.paper-2}"
    padding: "2px 6px"
    rounded: "3px"
  safety-selection:
    backgroundColor: "{colors.accent-soft}"
  research-select:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  behavior-meter:
    backgroundColor: "{colors.safety-accent}"
    height: "8px"
    width: "100%"
  explorer-card:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.lg}"
    padding: "16px 24px"
---

# Design System: GeoCrash

Synthetic pilot finish review, 2026-09-29: independent reviewer disposition **SHIP**. At 1440px and 390px, the synthetic banner, invented inspector/interval wording, scenario warning, synthetic CSV labeling, area-reset behavior, and hidden research sections passed with no JavaScript errors or viewport overflow. This verifies the demonstration interface, not model validity or commercial rights. Browser evidence: `/tmp/geocrash-ui-check/pilot-confirm-desktop.png` and `pilot-confirm-mobile.png`.

## Overview

**Creative North Star: "Cobalt Workbench"**

GeoCrash uses cool paper, dark technical typography, restrained cobalt actions, and compact evidence displays. Rules and aligned columns organize the workbench; maps and satellite imagery provide content in the existing explorer. The safety workspace extends this established identity.

Density follows the task. Analytical surfaces keep labels, units, and explanations near values. The existing map homepage uses floating panels; the safety workspace uses flush sections and an adjacent inspector. These are distinct layouts within the same visual system.

**Key Characteristics:**

- Cool neutral surfaces with cobalt interaction cues.
- Precise typography and aligned numeric comparisons.
- Ruled analytical sections with restrained corners.
- Evidence limitations visible beside the affected decision.

Implementation sources: `web/static/tokens.css`, `style.css`, `home.css`, and `safety.html`, `safety.css`, `safety.js`, `safety-evidence.js`, `models.html`, `models.css`, `advanced-models.js`, `metro-models.js`. The frontmatter records existing primitives and observed component variants. Surface briefs live at `.impeccable/surfaces/web-static-safety-html.md` and `.impeccable/surfaces/web-static-models-html.md`. The model and recorded-factor additions preserve this visual world in Operate mode. The public observatory adds `web/public/index.html`, `app.css`, and `app.js`; its implementation brief is `web/public/SURFACE.md` and registered surface brief is `.impeccable/surfaces/web-public-index-html.md`.

The public 3D homepage in `web/public/home.html`, `home.css`, and `home.js` restores the incumbent explorer’s full-viewport geographic presentation. Its registered brief is `.impeccable/surfaces/web-public-home-html.md`. The analytical observatory remains a separate light workbench at `/explore/`; this addition does not replace its visual system.

## Colors

The palette is cool and low-chroma except for action and semantic colors. Preserve the source OKLCH values.

### Primary

- **Cobalt / accent:** shared action color in the incumbent explorer.
- **Safety cobalt / safety-accent:** the safety stylesheet locally overrides `--color-accent` with this darker value. It colors primary actions, route links, current navigation, model interval marks, and recorded-factor meter fills. Research selection uses the shared pale cobalt row treatment, with the selection criterion written in the status text. The finish review measured approximately 4.915:1 against paper.
- **Pale cobalt / accent-soft:** selected table rows and existing search focus treatment.
- **Focus cobalt / focus:** keyboard outlines; remains the shared token on the safety page.

### Neutral

- **Cool paper / paper:** page and control background; also the light text on dark actions.
- **Inset paper / paper-2:** control groups, table headers, inline explanations, and diagnostics.
- **Technical ink / ink:** headings and primary values.
- **Supporting ink / ink-2:** body explanations and secondary labels in the safety workspace.
- **Muted ink / muted:** small supporting labels in the incumbent explorer.
- **Rule / rule and rule-strong:** section boundaries and control outlines, respectively.
- **Graphite / graphite and graphite-ink:** existing map context and dark analytical bands; safety uses the light workbench surface.

### Semantic

- **Risk / risk:** errors and established adverse data indications.
- **Safe / safe:** existing favorable data indications.
- The safety exposure notice has a local warm-paper treatment: `oklch(96% .025 80)` background, `oklch(34% .065 60)` text, and `oklch(84% .055 80)` border. It is a notice treatment, not a second brand accent.

**The Meaningful Color Rule.** Use cobalt for interaction and selection; retain explicit text for uncertainty and status.

Public observatory variants retain the palette while using public-muted for supporting labels, public-rule-strong for control outlines, and public-risk for error text. These are local contrast adjustments, not a replacement visual world.

The 3D home uses its extracted home-* tokens for a dark geographic canvas, light floating filters and summary, technical ink, subdued labels, cobalt actions and thin light-panel rules. Blue columns vary monotonically with crash counts; their color never encodes severity or exposure-adjusted risk.

## Typography

**Display:** Space Grotesk with the shared sans-serif fallback stack. **Body:** Inter with the shared sans-serif fallback stack. **Identifiers and technical labels:** JetBrains Mono with monospace fallback.

The safety document declares these families through tokens but does not load webfont files. Its appearance must remain usable with system fallbacks; do not describe custom font loading as verified there.

The shared report uses the display, body, and label roles in frontmatter. The safety page uses its denser body role, a headline that reduces to 27px on small screens, section titles, and 15px subheads. Table text is 13px, supporting explanations 12–13px, and segment identifiers 11px. Scenario figures use 24px display text at weight 500. The research page requests the three shared font families through its existing webfont stylesheet; its comparison cells use 13px monospace numbers and body-font model names. Advanced research notes are 13px, calibration annotations 11px/1.5, and report details 12px/1.6 monospace. Omaha table captions use 15px/1.5 body text at weight 600; row headings use 13px/1.55 body text, and metric/reference annotations use 12px/1.5 supporting ink.

Use tabular numerals for comparative table cells, inspector values, and scenario results. General paragraphs have a 75ch maximum; longer source and table notes have their own observed limits. Keep source qualifications legible without making them compete with headings.

The public 3D home declares the existing Space Grotesk/Inter families with system fallbacks and loads no remote webfonts. Its two-line display headline scales from 48–76px on desktop, reducing to 49px on mobile and 40px in short mobile viewports. Panel counts use 42px tabular display figures, reducing to 36px on mobile.

## Layout

Shared analytical grammar: a flush toolbar, ruled content regions, aligned columns, and compact controls. The map homepage retains its full-frame map and floating panels; do not transplant its composition into every analytical surface.

The safety page centers content within a 1560px maximum width with 32px desktop padding. Its desktop workspace combines a flexible table with a 330px inspector. The results container scrolls independently with sticky headers and a 540px maximum height. The inspector uses a left rule, not an elevated card.

At 1050px and below, page padding becomes 24px and the inspector narrows to 290px. At 740px and below, page padding becomes 20px vertically and 16px horizontally; the inspector follows the table; the table retains horizontal scrolling and a 380px maximum height. The primary load action spans the control group. Cost fields and results become two columns, and evidence becomes one column. Navigation can scroll horizontally.

Safety model and recorded-factor tables retain horizontal scrolling without the screening table's maximum-height limit. Their first column has a 170px minimum; section headers wrap, with 10px cell padding on mobile. Native factor meters are 8px high, full width with a 90px minimum, and sit 7px below the numeric share.

The research document keeps its 1040px maximum-width column and 24px horizontal padding. Comparison tables have a 640px minimum width inside a keyboard-focusable horizontal scroll region; their model-name column has a 210px minimum. Research controls wrap with 16px gaps and 6px label-to-field spacing. At 700px and below, page padding is 16px, the protocol label occupies a full row, selects fill their labels, and Refresh comparison spans the row. The report detail region wraps long content and scrolls at a 320px maximum height.

The corrected Omaha section comes first on the research page, followed by neural comparisons and the historical leaderboard. The historical future/random protocol control sits beside its own results. Omaha reuses research control stacking and focusable scroll regions; its captions wrap within `calc(100vw - 32px)` with 18px top and 8px bottom padding. Below 700px a 12px sideways-scroll hint appears.

The spacing scale in frontmatter remains the shared rhythm. Preserve local density adjustments when extending the safety surface; its current composition is documented in the surface brief.

The public observatory has a 1560px maximum container with 40px desktop gutters, reducing through 24px to 16px on small screens. Its geographic workspace pairs a flexible plot with a 290px state comparison rail; the rail narrows to 240px below 1100px and stacks below 800px. Model and source sections use ruled two-column layouts and stack for narrow screens. Tables scroll locally rather than widening the viewport. Observed public breakpoints are 1300px, 1100px, 800px, and 520px.

The 3D homepage uses a fixed full-viewport canvas, upper floating filter/navigation row, lower-left introduction and city presets, and an upper-right 277px summary panel. Below 760px, the filter row wraps below navigation and the initial hero becomes a lower-screen block; selecting a state or cell replaces it with a bottom summary panel. A fixed bottom legend retains the count interpretation and cell threshold. At 1100px the panel narrows and the extra screening navigation link hides while the primary screening CTA remains.

## Elevation & Depth

The analytical workbench primarily uses tonal surfaces and thin rules. The safety page has no ambient panel shadows; its current-navigation inset shadow is an underline. Existing explorer overlays use shadows to separate controls from map imagery: report search suggestions use `0 8px 24px oklch(24% 0.02 258 / 0.08)`, and homepage cards use `0 6px 24px oklch(10% 0.02 258 / 0.25)`.

**The Surface Context Rule.** Keep analytical sections flush; reserve existing overlay elevation for content floating over a map.

The 3D home’s map overlays reuse the explorer’s elevated-surface role: filters use `0 8px 30px #0003`, the summary uses `0 10px 35px #0003`, and the recovery card uses `0 10px 40px #0008`. Directional dark gradients behind foreground copy preserve map legibility. They are static content overlays, not ambient motion.

## Shapes

Small and medium corners soften controls and contained groups without changing the workbench's rectangular structure. The safety page uses the small radius for controls, notes, and table containment, the medium radius for area selection, and local 3px corners for status tags. The larger shared radius belongs to existing explorer cards and search surfaces. Tables and major content boundaries remain straight ruled edges.

## Components

- **Primary and secondary actions:** safety controls have a 40px minimum height. Primary actions use safety cobalt with light text and weight 600; hover uses supporting ink. Secondary actions stay on paper, with a stronger border and inset-paper fill on hover. Disabled controls use 0.5 opacity and a disabled cursor.
- **Fields:** native selects and number inputs use strong outlines, small corners, and visible labels. Safety keyboard focus uses a 3px outline with 3px offset. Checkboxes remain native and have explicit explanatory labels.
- **Navigation:** a flush ruled header, dark wordmark, and text links. Current navigation uses cobalt text and a 2px inset underline. The safety header changes to stacked content on small screens.
- **Status tags:** small neutral rectangular labels; communicate state through text, without implying approval through color.
- **Explorer cards:** existing floating map panels use paper, the large radius, and the overlay shadow described above. The safety inspector is a ruled section rather than this card variant.
- **Screening table and inspector:** sortable headers expose direction with arrows and `aria-sort`; selected routes use pale cobalt and `aria-pressed`. Right-aligned tabular numbers support comparison. The inspector pairs labels and values, an exposure-status note, and an accessible interval graphic where data is available.
- **Evidence notices:** warm exposure notice, plain statewide linkage statement, inline proxy note, source register, and expandable diagnostics. Preserve proximity to the values they qualify. API values supply periods, coverage, and results; example figures must never become hardcoded product facts.
- **Model comparisons:** safety offers later-year and unseen-area protocols; research offers later-incident and unseen-area later-incident protocols plus reporting-source inclusion/exclusion. Preserve each table's own metrics and split context. Research selectors and refresh use paper, 4px corners, 8px 12px padding, and a 42px minimum height; research keyboard focus is 2px with 2px offset. A pale cobalt row identifies the validation-selected model, with the criterion stated in text; it does not imply external validation or deployment approval.
- **Omaha comparisons:** a native evaluation selector offers frozen future, frozen future in unseen areas, and monthly updates. The duration-objective selector applies only to frozen results and hides for monthly evaluation. Frozen metrics pair the selected estimate with its corrected reference beneath; monthly tables compare training schedules. Row headers and captions identify the task, while disclosures expose class support, recall, blend members, intervals, training boundaries, and data drift. C imagery labels describe the global-median fallback and explicitly state that reporting source is not an input, including in the details. The API supplies evidence; archived original results remain accessible below.
- **Recorded factors:** labeled geography and year selectors precede a table of recorded yes, recorded no, unknown, not applicable, and share among known cases. Pair each cobalt meter with its numeric share and available interval. Keep factor definitions, missingness, and source evidence in expandable details; recorded crash findings do not establish driver intent or population risk.
- **Reproducible details:** native disclosure controls reveal methods and reports; report text uses inset paper, 16px padding, wrapping, and independent scrolling. Safety keeps its complete report nested below methods; research details include calibration, split boundaries, and the selected experiment.
- **Scenario results:** a ruled numeric strip with plain labels and expandable calculation details. Required applicability and transfer acknowledgments gate calculation; changing assumptions clears old output.
- **Synthetic demonstration state:** the same workspace changes its title and primary notice to identify invented roads, counts, exposure, predictions and intervals. Fictional corridor identifiers and synthetic export filenames preserve that distinction outside the page. Official model/recorded-factor sections and their navigation links hide in this mode; safety-only navigation omits unavailable research routes. The notice reuses the existing warm-paper treatment with explicit text, adding no new palette, layout or animation.
- **Public 3D home:** the local deck.gl scene combines state boundaries and hexagonal extruded count columns. Native state/year controls, city camera presets, zoom, 3D/flat toggle, reset view and national reset complement direct map selection. City presets explicitly retain state-level totals. Column heights use a square-root transform of observed counts; clickable cells expose exact counts and the aggregate center. The light filter and summary surfaces use 9px corners, actions generally 5–6px, and city presets 20px pills, all within this map-overlay context. Keyboard focus is 3px pale blue with 4px offset.
- **Public 3D movement and recovery:** user-triggered camera flights take 1100ms and become immediate under reduced motion. There is no ambient camera motion. WebGL/library failures show a recovery card with retry and a link to the analytical explorer. Data failures retain previous results with explicit status. A skip link gives keyboard users direct access to data tables, while a no-script message points to API documentation and summary JSON.
- **Public geographic explorer:** native state/year selectors update the map, summary, annual records and recorded-factor cohort together. Keyboard-selectable state boundaries and a numeric ranking rail provide equivalent geographic entry points. The map uses local Census-derived boundaries, separate Alaska/Hawaii insets, and explicit sparse-cell coverage; map symbols represent counts, not normalized risk.
- **Public count inference:** the selected geography preselects a separate forecast form, but the model runs only on an explicit action. Results retain their frozen prediction year, observed-year reference, held-out baseline and limitations. Public buttons/selects generally use 44px minimum heights and 3px focus outlines with 3px offset.
- **Loading, empty, and error states:** text remains in the relevant result region; load and calculation messages use live regions. Errors include a recovery action. No decorative motion is added to the safety workflow; smooth anchor scrolling switches off for reduced motion.

Omaha extension finish review: `metro_finish_reviewer` disposition **SHIP** after resolving the C-imagery source-median label in both the table and details. Browser checks passed for both frozen protocols, both duration objectives, monthly evaluation, and error recovery at 1440px and 390px, with no viewport overflow or JavaScript errors. Existing font and radius detector advisories remain incumbent observations; no visual-world replacement is implied.

Public observatory finish review, 2026-09-29: independent `public_finish` disposition **SHIP**, with no material fixes. Desktop 1440px and mobile 390px checks covered actual data, navigation links, screening, runtime inference, scenario guards, invalid inputs and unavailable research routes; there were no JavaScript errors or viewport overflow. Evidence: `/tmp/geocrash-ui-check/public-review-{1440,390}.png` and `public-screening-{1440,390}.png`. This is interface and implementation verification, not agency approval.

Public 3D homepage finish review: independent `home_finish_reviewer` disposition **SHIP**, with no outstanding material issues. Desktop 1440px and mobile 390px checks exercised WebGL, real counts, Nebraska filtering, tilt/reset, Alaska/Hawaii, API-error recovery and unavailable-WebGL fallback. Mobile line-break spacing was repaired after inspection. This adds an experiential entry surface while preserving the analytical workbench.

## Do's and Don'ts

- Do preserve the established Cobalt Workbench when adding analytical surfaces.
- Do align comparable numbers and keep units, source periods, and limitations beside decisions.
- Do retain visible keyboard focus and explicit selection and sorting semantics.
- Do adapt layouts to the viewport while preserving access to the complete table.
- Don't turn modeled results into visual claims of verified outcomes.
- Don't substitute decorative cards for the safety workspace's ruled sections.
- Don't use color alone to communicate selection, uncertainty, or readiness.
- Don't assume declared font families are loaded on every surface.

## Agency planning surface — 2026-09-30

`/planning/` carries the existing restrained public visual language into seven keyboard-accessible workflow tabs. Real road selectors, required assumptions and calculation summaries precede expandable technical output. Downloadable evidence remains attributable to inputs; cash, capacity and societal value remain visibly distinct. No fake customer data is preloaded. At 390px, form columns collapse without horizontal overflow. The home navigation includes Agency planning; mobile map controls and source caption are positioned below the wrapped navigation. OSM attribution and dated Geofabrik source appear next to generated routes.
