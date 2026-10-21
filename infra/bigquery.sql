-- Template: replace YOUR_PROJECT with an existing project before execution.
-- Only approved safety artifacts belong here; never load legacy Kaggle tables.
CREATE SCHEMA IF NOT EXISTS `YOUR_PROJECT.safety` OPTIONS(location='US');
CREATE TABLE IF NOT EXISTS `YOUR_PROJECT.safety.segments` (
  snapshot_date DATE,
  segment_id STRING,
  geometry GEOGRAPHY,
  aadt FLOAT64,
  aadt_year INT64,
  length_miles FLOAT64,
  source STRING,
  properties JSON
) PARTITION BY snapshot_date CLUSTER BY geometry;
CREATE TABLE IF NOT EXISTS `YOUR_PROJECT.safety.crashes` (
  crash_id STRING,
  year INT64,
  geometry GEOGRAPHY,
  fatalities INT64,
  source STRING
) PARTITION BY RANGE_BUCKET(year, GENERATE_ARRAY(2015, 2101, 1)) CLUSTER BY geometry;
-- Example proximity query, parameterized in metres:
-- SELECT * FROM `YOUR_PROJECT.safety.segments`
-- WHERE snapshot_date=@snapshot_date
-- AND ST_DWITHIN(geometry,ST_GEOGPOINT(@lng,@lat),@radius_metres);
