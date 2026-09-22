# HTTP cassettes for shape-B records (record and replay)

Status: **design only, not implemented**. `inspect_tasks.py` refuses to score
a record whose `sandbox.network` is `replay` and voids it with a reason; a
record-mode run (`--allow-live-network`, `network: allowlist`) is allowed but
its rows are flagged `network_live`. The argument for this design is in
`DESIGN.md §5.3`; this file is the contract the implementation must meet.

## What a cassette is

One YAML file per record (or per shared data window), listing recorded HTTP
exchanges against the live services a task may touch:

| Service | Host | Determinism for a fixed past window |
|---|---|---|
| EarthScope FDSN dataselect / station | `service.earthscope.org` (was `service.iris.edu`, now a 307) | High; MiniSEED for a past window is stable unless re-archived |
| OOI M2M synchronous JSON | `ooinet.oceanobservatories.org/api/m2m/12576/sensor/inv/...` | High for past windows; response carries provenance ids |
| OOI M2M asynchronous (NetCDF via THREDDS) | same host + THREDDS | Low: job-specific URLs; match on the canonical request, serve the recorded NetCDF |
| PI portals | `piweb.ooirsn.uw.edu/...` (Apache directory listings) | Medium: listings grow as files are added; match by path, serve the recorded listing |

## Matching key (replay)

`method + host + path + canonicalised query` where the query is sorted, has
`beginDT/endDT/start/end` normalised to ISO-8601 UTC seconds, and ignores any
authentication parameter or header. Headers are not part of the key.

## Credentials

The OOI API username and token are held by the recording proxy and injected
into outbound M2M requests. They never enter the sandbox. In replay mode no
credential exists anywhere in the run.

## Misses

A request with no cassette match receives HTTP 599 and a JSON body that says
so. The sample is scored as a **failure** (not a void) and tagged
`replay_miss` with the request key, so authors can decide whether to extend
the cassette (a legitimate alternative route) or leave it (a wrong request).

## Files

```
cassettes/<name>.yaml         # public windows only
private/cassettes/<name>.yaml # hidden split, hosted per docs/golden_data_provisioning.md Mode B
```

Each cassette carries `recorded_at`, the recording run id, the proxy
version, and a sha256 per response body. The record's `sandbox.cassette`
names the file; `validate.py` will check the hash once the format exists.
