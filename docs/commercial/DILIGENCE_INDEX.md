# Technical and procurement diligence index

This index maps questions to existing evidence and required follow-up. Documents and local artifacts are for review in the workspace; a relative link is not an externally accessible data room. Package only approved materials for a particular recipient.

## Evidence inventory

| Buyer question | Evidence | What it establishes |
|---|---|---|
| Can we inspect real data and working inference? | [Public deployment guide](../PUBLIC_DEPLOYMENT.md), [public verifier](../../scripts/verify_public.py) | Historical federal explorer, state count inference, Nebraska road screening and public APIs; 3D-release anonymous verification passed in `outputs/releases/public-3d-verification.json` |
| Can we try the workflow without agency data? | [Synthetic generator](../../safety/demo.py), [demo script](DEMO_SCRIPT.md) | 24 invented examples with explicit labeling; no accuracy evidence |
| What goes into an evaluation package? | [Release tooling](../../safety/release.py), [buyer guide](README.md) | Explicit code/documentation allowlist, exclusion of datasets and credentials, per-file checksum manifest |
| How is release readiness checked? | [Release audit and operations](../OPERATIONS.md), [smoke script](../../scripts/smoke_safety.py) | Offline artifact integrity plus separate serving checks; commercial readiness remains false |
| Can a code release be reverted? | [Rollback helper](../../infra/rollback-cloud-run.sh), [operations](../OPERATIONS.md) | Restore traffic to an existing revision; shared data and jobs require separate recovery |
| What does the system do? | [Buyer brief](BUYER_BRIEF.md), [product definition](../../PRODUCT.md), [README](../../README.md) | Scope and workflow |
| How are counts, exposure, and EB calculated? | [Methods](../SAFETY_ENGINE.md), [model artifact](../../data/safety/model.json) | Equations, assumptions, fitted snapshot |
| Which sources were used? | [FARS manifest](../../data/safety/fars-manifest.json), [AADT manifest](../../data/safety/aadt-manifest.json) | Hashes, release years, retrieval dates, traffic-rights flag |
| How strong is the predictive evidence? | [Advanced models](../ADVANCED_MODELS.md), [benchmark artifact](../../data/safety/advanced-benchmark.json) | Internal holdout comparisons and limitations |
| Are research assets separated? | [Operations](../OPERATIONS.md), [production Dockerfile](../../Dockerfile), [cloud upload allowlist](../../.gcloudignore) | Declared deployment boundaries; verify packaged release too |
| Has cloud deployment actually worked? | [Dated advanced deployment verification](../../outputs/reports/CLOUD_ADVANCED_VERIFICATION.json) | Recorded authenticated service, warehouse, model-evidence and isolation checks |
| Have scheduled jobs completed? | [Initial cloud verification](../../outputs/reports/CLOUD_VERIFICATION.json) | Recorded feed and candidate job executions; not ongoing availability |
| How are failures and promotion handled? | [Operations](../OPERATIONS.md), [cloud job wrapper](../../safety/cloud_job.py) | Freshness, retained last-successful feeds, leases, completion markers, manual promotion |
| What procurement work remains? | [Procurement checklist](../PROCUREMENT.md), [SOW](PILOT_SOW.md) | Required rights, access, operations and acceptance decisions |
| What is proposed research? | [Foundation architecture](../FOUNDATION_ARCHITECTURE.md), [disabled configuration](../../configs/foundation/roadworld_scratch.json) | Planned model design and evaluation gates, not trained capability |
| What proves customer benefit? | [Pilot evaluation protocol](../PILOT.md) | Prepared process; outcome evidence still to be collected |

## Release-specific review record

For an actual buyer review, record release/image digest [ ], snapshot hash [ ], source manifests [ ], verification date [ ], test report [ ], dependency/security scan [ ], access configuration [ ], approved audience [ ], and evidence owner [ ]. Do not silently treat the September 29 evidence as verification of a later release.

The handoff records prior passing safety tests and coverage, but a procurement packet should attach the exact test output from the offered release. Hosted CI configuration exists; a hosted run is not established merely by the presence of a workflow file.

## Decisions to close before commercial delivery

| Decision | Required record | Suggested accountable role |
|---|---|---|
| NDOT or replacement-source rights | Written permitted use, derivatives/redistribution, attribution and retention | Supplier owner and provider/agency data steward |
| Supplier software terms | Selected code/software license and contracting entity | Supplier owner |
| Customer data use | Executed scope, transfer/access terms and deletion/return plan | Customer data owner |
| Experimental model acceptance | Independent evaluation, linkage review, documented limitations | Transportation engineer and sponsor |
| Access and deployment | Named users, isolated environment, identity and secret-management review | Customer and supplier technical leads |
| Security and incident handling | Review results, incident contacts, retention and response commitments | Security/operations owner |
| Reliability and recovery | Restoration drill and accepted support/recovery targets | Operations owner |
| Fees and delivery | Completed SOW, acceptance/rework rules, cloud cost responsibility | Commercial representatives |
| Case study or logo use | Separate explicit publication permission | Customer communications/authorized representative |

## Sharing rules for the packet

Share the buyer brief and an agreed scope first. For technical diligence, provide a reviewed evidence bundle with only the permitted artifacts. Cloud reports may include account identifiers, project metadata and job logs; redact unnecessary identifying metadata in a separate review copy, preserving the original evidence internally. Never include `.cloud-config`, credentials, OAuth codes, secrets, raw personal data, or noncommercial research weights in a buyer package.

Rights-restricted road outputs remain restricted even when included in a ZIP or PDF. If an artifact cannot be shared, offer an authorized screen-shared review, a summary approved for disclosure, or a synthetic example explicitly labeled as synthetic.

The code-only evaluation ZIP intentionally omits real datasets, research artifacts, and cloud verification reports. Evidence links into those locations are workspace references, not a promise that the ZIP contains them. Include permitted review copies separately and record their hashes.
