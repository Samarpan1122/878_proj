# Buyer discovery and outreach drafts

These drafts have not been sent. Replace placeholders with verified information and select one recipient whose role matches the proposed use case.

## Discovery agenda

Open with the decision: “Which road-safety prioritization task consumes time or produces disputed results today?” Then establish the following before discussing model architecture.

| Topic | Questions | Why it changes scope |
|---|---|---|
| Decision and owner | Who creates the shortlist, who approves it, and what action follows? | Identifies the workflow and accountable reviewer |
| Current baseline | Are locations ranked by counts, rates, an existing SPF/EB method, or a consultant report? What is already working? | Defines a fair comparison |
| Network and outcome | Which roads, years, facility types, and crash outcomes matter? | Determines eligible data and model task |
| Data access | Can you supply dated road geometry, annual AADT, stable segment IDs, and permitted crash records? Who can approve use and outputs? | Establishes feasibility and rights |
| Known errors | How often are junctions, ramps, frontage roads, or duplicate records corrected manually? | Focuses linkage auditing |
| Evaluation | What shortlist size or road-mile budget is meaningful? How is analyst effort recorded? What would make the result unacceptable? | Produces measurable acceptance criteria |
| Integration | Do users need a hosted workspace, CSV handoff, GIS integration, or an API? Is a separate agency environment required? | Bounds delivery work |
| Security and procurement | Which access, retention, contracting, security-review, and purchasing requirements apply? Who owns each review? | Sets dependencies before commitment |
| Commercial fit | Is there a budget owner and a process for a fixed-scope evaluation? What approval follows a successful pilot? | Tests whether a real next step exists |

Do not ask the prospect to email record-level sensitive crash data during discovery. Identify an approved transfer path after an agreement and access design exist.

## Meeting notes template

- Organization / attendees / roles / date:
- One decision to improve:
- Current method and pain point:
- Proposed geography, outcome, and time period:
- Data owner, permissions contact, and available source vintages:
- Analyst, engineering reviewer, and budget/procurement owner:
- Proposed acceptance measures and exclusions:
- Security/integration dependencies:
- Agreed next step, owner, and date:
- Permission to reference the organization publicly: not granted unless explicitly recorded.

## Agency or engineering-consultancy email

**Subject:** A scoped road-safety screening evaluation for [network or jurisdiction]

Hello [name],

I am building GeoCrashAI, an auditable workspace for reviewing fatal-crash history alongside traffic exposure and Empirical Bayes screening. It includes source provenance, baseline comparisons, and documented countermeasure scenarios.

I can demonstrate the workflow with clearly labeled synthetic roads. The separate Nebraska evaluation is experimental: its traffic counts are historical proxies, and data permissions need confirmation for commercial delivery. I am looking for a partner to define a bounded evaluation using approved data and an existing prioritization workflow.

Would a short conversation with your safety analyst and engineering reviewer be useful to assess the fit? I can demonstrate the workflow and share a proposed pilot scope covering data quality, a frozen shortlist comparison, and analyst effort.

Best,
[name]
[role / organization]
[contact]

Attach or link the reviewed buyer brief using your chosen sharing channel. Do not attach underlying data, private cloud verification records, or an unapproved public service link.

## Technology-company evaluation email

**Subject:** Road-safety screening workflow — technical evaluation opportunity

Hello [name],

I have built GeoCrashAI, a road-safety screening workflow with official fatal-crash ingestion, traffic-exposure accounting, statistical network screening, and reproducible evidence. A separate synthetic demonstration and code-only evaluation package support an initial technical review. The safety service runs privately on Google Cloud, separate from the noncommercial research explorer.

I would value a technical discussion about whether this workflow fits [specific, verified team responsibility]. The current evidence is retrospective and experimental; I can walk through the deployed workflow, source lineage, baseline comparisons, and what an independent evaluation would require.

There is also a detailed proposal for a multimodal road representation model. It is a research roadmap, not a trained foundation-model claim.

Would [a proposed meeting window] work for a brief technical introduction?

Best,
[name]
[contact]

## After a qualified conversation

Send a concise recap with the agreed decision, data owner, acceptance measures, dependencies, and next meeting. Use the [SOW template](PILOT_SOW.md) only after scope is established. Partnership names, logos, case studies, and public results require explicit permission. Acquisition interest is a separate external outcome; do not imply it from a meeting or cloud deployment.
