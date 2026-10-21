# Private Nebraska routing backend

This service builds an OSRM MLD car-routing graph from Geofabrik's dated Nebraska
OpenStreetMap extract. Data preparation happens entirely on Cloud Build; the local
submission contains only the small infrastructure files in this directory.

- Engine: official OSRM `v26.9.0-amd64-debian`, immutable image digest in Dockerfile.
- Input: `https://download.geofabrik.de/north-america/us/nebraska-260926.osm.pbf`.
- Profile: the engine image's unmodified `/opt/car.lua`.
- Algorithm: `osrm-extract`, `osrm-partition`, then `osrm-customize` (MLD).
- Runtime identity: UID/GID 65534; prepared data must be owned by that UID because
  some OSRM artifacts have owner-only permissions. A real route smoke test runs
  as UID 65534 before the image is pushed.
- Input SHA-256: `a0caa806aabbe2fb2ef3738cc6af3248f8130021f837d553258b4bc6c6be2273`.
  Emitted in build logs, bundled as `/data/SOURCE-SHA256.txt`, and required by future builds.
- Licensing/attribution: OSM contributors, ODbL 1.0; engine BSD 2-Clause. See NOTICE.txt.
- Reproduction: download the identical source bytes, verify the recorded SHA-256,
  and run the pinned image with the three preparation commands in cloudbuild.yaml.
  Geofabrik's retention of dated source downloads is not guaranteed; preserve a
  copy of the matching source before a future rebuild if that date is removed.

Submit only this directory:

```sh
gcloud builds submit infra/routing --project=PROJECT \
  --config=infra/routing/cloudbuild.yaml \
  --substitutions=_IMAGE=us-central1-docker.pkg.dev/PROJECT/geocrash/routing:osrm-26.9.0-nebraska-20260926
```

Run with a dedicated service account that has no project roles. Cloud Run uses
one CPU, 2 GiB memory, zero minimum instances, one maximum instance, concurrency
four, a 30-second request timeout, and a 240-second TCP startup allowance. Require
IAM authentication; grant `roles/run.invoker` on this service only to the public
application's existing runtime service account.

Set these on the public application, using the routing service's canonical URL:

```text
SAFETY_ROUTING_OSRM_URL=https://PRIVATE_ROUTING_SERVICE.run.app
SAFETY_ROUTING_AUTH_AUDIENCE=https://PRIVATE_ROUTING_SERVICE.run.app
```

The application obtains a Google identity token using runtime identity. No service
account key is created or stored. Redirects are rejected to prevent forwarding the
token to another origin. Routing requests are throttled in each application
instance. Cloud Run request logs can contain route coordinates in OSRM's URL;
the application itself does not persist submitted trips.

This is frozen baseline route planning, not live traffic navigation. The graph
has no live closures, congestion feed, vehicle-dimension profile, or service-level
agreement. Historical risk is a separate experimental overlay; it does not alter
the routing graph's edge weights. Public attribution must accompany maps and route
outputs, and ODbL source/reproduction information must remain available.
