# Agency pilot readiness and procurement evidence

The present system is an experimental screening workspace. Procurement readiness depends on verified evidence and agency acceptance; a functioning cloud deployment is not certification or a service-level commitment.

| Review area | Evidence available or required |
|---|---|
| Data contracts | Source manifests and legacy-data isolation exist. Obtain written NDOT commercial/redistribution terms and an agency agreement before importing record-level state crashes or connecting 511. |
| Reproducibility | Preserve input hashes, exact source vintages, model configuration, linkage exclusions, temporal/spatial validation, and the approved snapshot. Re-run results from the frozen artifacts. |
| Method review | A transportation engineer must review facility types, exposure vintage, crash matching, SPF calibration, EB uncertainty, and every proposed treatment's applicability. Current FARS output is fatal-crash screening only. |
| Private access | Keep an agency pilot authenticated through Cloud Run IAM or an approved identity layer. Public demo access is a separate deployment decision; never add agency identifiers to its artifacts. The app currently has no tenant isolation or per-user role model. |
| Security | Named service accounts, bounded exports, and source isolation exist. Complete dependency scanning, secret rotation, IAM review, audit-log retention, incident-response ownership, and a penetration review before a sensitive production contract. Do not claim SOC 2 or equivalent certification. |
| Operations | Assign owners for failed refreshes, stale feeds, source releases, candidate approval, backup restoration, cloud spend, and lease recovery. Test each recovery procedure. Availability and response-time SLAs have not been agreed or demonstrated. |
| Human decisions | Rankings support investigation; they do not approve engineering changes or forecast an individual's collision. Record reviewer decisions and retain countermeasure assumptions and sensitivity results. |
| Pilot success | Pre-register baselines, holdout periods, shortlist size, analyst-effort measures, and acceptance criteria with the partner. No secured pilot, demonstrated crash reduction, or agency endorsement is claimed. |

Before contract signature, prepare a scope of work defining geography, allowed users, supported data feeds, retention/deletion, export rights, review responsibilities, support hours, incident notification, and termination/data return. Separate proposed targets from measured service history. Use `docs/PILOT.md` for the evaluation protocol and `docs/OPERATIONS.md` for current deployment and recovery procedures.

## Warehouse load evidence

`safety.warehouse.export_bigquery(root, output_dir)` creates `segments.ndjson`, `crashes.ndjson`, explicit JSON schemas, and a checksum/count manifest. Road geometry is WGS84 WKT. Unlocated crashes remain present with null geography. Screening statistics are attached as native JSON objects, following [BigQuery's NDJSON JSON-column format](https://cloud.google.com/bigquery/docs/json-data#load_from_newline_delimited_json_files); WKT requires an explicit [GEOGRAPHY schema](https://cloud.google.com/bigquery/docs/geospatial-data#loading_wkt_or_wkb_data).

For the concrete project `geocrashai-safety-20260929`, create the `safety` dataset using `infra/bigquery.sql` after replacing `YOUR_PROJECT`. Load the generated files with the corresponding schema files and `NEWLINE_DELIMITED_JSON`. Compare warehouse row counts and null-geography counts to `manifest.json` before accepting the load. Keep tables private. These schema commands provision no agency partnership or data rights.

```bash
# These commands create/replace only the dedicated experimental warehouse tables.
bq --project_id=geocrashai-safety-20260929 --location=US load \
  --replace --source_format=NEWLINE_DELIMITED_JSON \
  geocrashai-safety-20260929:safety.segments \
  EXPORT_DIR/segments.ndjson EXPORT_DIR/segments-schema.json
bq --project_id=geocrashai-safety-20260929 --location=US load \
  --replace --source_format=NEWLINE_DELIMITED_JSON \
  geocrashai-safety-20260929:safety.crashes \
  EXPORT_DIR/crashes.ndjson EXPORT_DIR/crashes-schema.json
```
