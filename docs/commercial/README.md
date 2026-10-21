# GeoCrashAI buyer and pilot package

Prepared September 29, 2026. This package supports a product demonstration, technical evaluation, and scoped pilot discussion. The offered initial product is a road-safety screening workflow; the foundation-model architecture is a separately identified research proposal.

## Use this package

| Meeting or task | Document |
|---|---|
| Send a short product introduction | [Buyer brief](BUYER_BRIEF.md) |
| Run a ten-minute demonstration | [Demo script](DEMO_SCRIPT.md) |
| Qualify a prospective buyer and prepare outreach | [Discovery and unsent email drafts](DISCOVERY_AND_OUTREACH.md) |
| Agree a bounded evaluation | [Pilot statement of work template](PILOT_SOW.md) |
| Check a slide, proposal, or sales statement | [Capability and claims matrix](CLAIMS_MATRIX.md) |
| Answer technical and procurement questions | [Diligence index](DILIGENCE_INDEX.md) |

Start with the buyer’s current prioritization decision, demonstrate the actual historical FARS portal and Nebraska screening engine, and propose a measurable agency evaluation. The [public website](https://geocrash-666321636483.us-central1.run.app) is live without an account, with anonymous deployment checks passed on revision `geocrash-00002-vkd`. Use the [public deployment guide](../PUBLIC_DEPLOYMENT.md) to review evidence and refresh verification before a meeting. Selling a promised foundation-model breakthrough is outside the evidence on hand.

## Delivery boundary

The existing Nebraska dataset uses 2025 NDOT traffic counts as historical exposure proxies, and its commercial reuse terms are unconfirmed. Commercial export is restricted by the application. Obtain documented rights or use an approved replacement dataset before commercial delivery; do not change a manifest flag merely to unblock an export. Deployment and successful API checks do not grant those rights.

An appropriate first commercial structure is a negotiated, fixed-scope evaluation followed by an optional annual support/software agreement, each conditioned on approved data rights and acceptance criteria. No price, contract, service-level commitment, customer, or demonstrated crash reduction is established by these documents. The owner must also select software licensing and contracting terms.

The [public deployment guide](../PUBLIC_DEPLOYMENT.md) covers shareable website/API access, historical coverage, inference, request limits and rollback. The [operations guide](../OPERATIONS.md) covers the separate private deployment. The [pilot protocol](../PILOT.md) defines the scientific evaluation. This package turns those into meeting and delivery materials; it does not send outreach or sign agreements.

## Optional offline demonstration

The public real-data website is the primary buyer demonstration: [3D homepage](https://geocrash-666321636483.us-central1.run.app), [data and model workbench](https://geocrash-666321636483.us-central1.run.app/explore/), and [road screening](https://geocrash-666321636483.us-central1.run.app/screening/). Its source window is 2021–2024, the national projection is frozen for 2025, and its road estimates use 2025 traffic proxies. The [demo script](DEMO_SCRIPT.md) keeps those limits beside the evidence.

If internet access is unavailable, the optional offline demonstration uses **24 fictional corridors** and invented counts, exposure, predictions, and intervals. No model is trained by this generator and none of its outputs measures real road risk.

```bash
.venv/bin/python -m safety.demo --root data/synthetic-demo
GEOCRASH_SAFETY_DATA=data/synthetic-demo .venv/bin/uvicorn safety.api:app --host 127.0.0.1 --port 8893
```

Open http://localhost:8893. The generator requires a new or empty directory and preserves existing data. The page identifies synthetic data and hides official model/behavior sections. Keep the synthetic fixture separate from the public official-source service. NDOT’s publisher policy supports informational web use at the user’s risk; commercial redistribution terms remain unresolved.

## Prepare a reviewable release

```bash
.venv/bin/python -m safety.release audit --root data/safety --output outputs/releases/readiness.json --require-technical
.venv/bin/python -m safety.release bundle --output outputs/releases/geocrash-evaluation.zip
```

The first command checks the official-source artifact hashes and manifests. For the synthetic fixture, substitute `--root data/synthetic-demo`. A passing technical audit retains `commercial_ready=false`; permissions and agency acceptance remain external gates.

The ZIP uses an explicit allowlist and contains code, documentation, deployment files, a synthetic-data generator, and a checksum manifest. It excludes real datasets, account credentials, and trained research weights. Its included README explains startup in a clean extracted package. The notice makes clear that the owner must agree software distribution/commercial terms before sharing. Some diligence links refer to evidence intentionally omitted from the ZIP; request a permitted review copy when needed.

`/ready` checks serving readiness; `/api/safety/readiness` exposes the lighter metadata assessment. Use the [smoke and rollback procedures](../OPERATIONS.md) to verify a deployed release. Rollback of application traffic does not restore shared data or scheduled-job images.
