# PNSN catalog quickref

The Pacific Northwest Seismic Network (PNSN) operates ~400 stations across
Washington, Oregon, and southern British Columbia. Catalog access:

- FDSN event service: `Client("IRIS")` typically returns PNSN-authored events
  for `network in ("UW", "UO", "CC")`. Prefer `catalog="ANF"` or
  `contributor="UW"` when narrowing.
- Regional analyst catalog: events authored by PNSN are tagged with
  `agency_id="UW"` (Washington) or similar. Quarry blasts are typically
  flagged `event_type="quarry blast"` or `event_type="explosion"`.
- Catalog IDs follow the `uw<numeric>` convention (e.g., `uw10262801` for
  Nisqually 2001).

When associating a trigger with a regional event, query within ±30 s of the
trigger and within an epicentral distance compatible with the trigger's
estimated S-P time (or the observed amplitude if S-P picking is not feasible).

## Sources

- PNSN ANF catalog and station metadata: https://pnsn.org/
- IRIS DMC FDSN web services: https://service.iris.edu/
- ObsPy FDSN docs: https://docs.obspy.org/packages/obspy.clients.fdsn.html

Citing data from these services in any research use is mandatory; see
PNSN and IRIS data citation policies.
