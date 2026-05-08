# FDSN service quickref

| Service | Coverage                          | Client constructor      |
|---------|-----------------------------------|-------------------------|
| IRIS    | Global; most US regional networks | `Client("IRIS")`        |
| USGS    | USGS-authored events & waveforms  | `Client("USGS")`        |
| NCEDC   | Northern California               | `Client("NCEDC")`       |
| SCEDC   | Southern California               | `Client("SCEDC")`       |
| GFZ     | GEOFON, German networks            | `Client("GFZ")`         |
| ORFEUS  | Europe                            | `Client("ORFEUS")`      |

## Network and channel codes

- Network codes (e.g., `UW`, `BK`, `NC`, `CI`) follow the IRIS codes registry.
- Channel codes are FDSN SEED channels: `BHZ` (broadband, vertical), `HHZ`
  (high-broadband, vertical), `EHZ` (short-period vertical), and so on. The
  first letter encodes sampling rate, the second encodes instrument type, the
  third encodes orientation.
- Location code `""` (empty string) is normal for primary channels.
  `"00"` is sometimes used for a primary, `"10"` for secondary.

## Common pitfalls

- `Client("IRIS")` resolves to the IRIS DMC FDSN endpoint. If the user names
  a different service, use `Client(<name>)` rather than the generic URL.
- `attach_response=True` is only valid when the service returns response
  metadata; don't pair it with raw waveform-only services.
- `get_waveforms_bulk` is more efficient when fetching many traces, but for
  this benchmark suite single-trace fetches are fine.

## Citation

When fetched data are used in a publication, cite the network DOI (when
available) and the FDSN service used. PNSN, IRIS, NCEDC, and SCEDC each
publish citation guidance.
