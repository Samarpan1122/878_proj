# Official OSRM 26.9.0 amd64 Debian image, pinned to its registry digest.
FROM ghcr.io/project-osrm/osrm-backend@sha256:359bd596d4adde1bd55856f8b81b0f6459cb8774abd8558aaccb273c1ab2fa4b
LABEL org.opencontainers.image.title="GeoCrash Nebraska routing" \
      org.opencontainers.image.description="OSRM 26.9.0 MLD, Geofabrik Nebraska 2026-09-26, OSM contributors / ODbL" \
      org.opencontainers.image.source="https://github.com/Project-OSRM/osrm-backend/tree/v26.9.0"
COPY --chown=65534:65534 data/ /data/
COPY NOTICE.txt /data/NOTICE.txt
EXPOSE 8080
USER 65534:65534
ENTRYPOINT ["osrm-routed"]
CMD ["--algorithm", "mld", "--port", "8080", "--threads", "1", "--verbosity", "WARNING", "/data/nebraska.osrm"]
