"""Generate STA/LTA plot goldens for the FrugalMind benchmark.

For each event in `events.yaml`, fetch waveforms via FDSN, run the canonical
preprocessing + STA/LTA recipe, and write a reference PNG. SSIM scoring in
`STALTAPlotSuite` compares model output to these PNGs.

Two output modes:

  - public  (default)  → src/frugalmind_suites/sta_lta/data/golden/<id>.png
                          (committed; suitable for VERIFIED, citable events)
  - private (--private) → $FM_STALTA_GOLDEN_DIR/<id>.png
                          (gitignored; for VERIFY events still being validated)

Two data modes:

  - real      (default)   uses obspy + a live FDSN service
  - synthetic (--synth)   uses a deterministic stand-in suitable for sandboxes
                          and CI smoke tests; do not publish benchmark numbers
                          against synthetic goldens.

Examples:

    # Public goldens for the two verified events:
    python scripts/build_plot_goldens.py --only nisqually-2001 tohoku-2011-teleseism

    # Private goldens for the two VERIFY events most plausible to verify:
    FM_STALTA_GOLDEN_DIR=~/private/fm_goldens \\
        python scripts/build_plot_goldens.py --private \\
        --only pnsn-quiet-day-VERIFY mt-rainier-swarm-2024-VERIFY

    # CI / sandbox smoke (no network, deterministic):
    python scripts/build_plot_goldens.py --synth --only nisqually-2001 tohoku-2011-teleseism
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import yaml  # noqa: E402

from frugalmind_suites.sta_lta.recipe import (  # noqa: E402
    DEFAULT_STALTA,
    CanonicalPlotInput,
    render_canonical_plot,
    stream_to_canonical_input,
    synthetic_canonical_input,
)


PUBLIC_DIR = REPO / "src" / "frugalmind_suites" / "sta_lta" / "data" / "golden"
DEFAULT_EVENTS = REPO / "src" / "frugalmind_suites" / "sta_lta" / "events.yaml"


def _load_events(path: Path) -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("events", []) or []


def _params_for(event: dict) -> dict:
    sp = event.get("stalta_params") or {}
    defaults = DEFAULT_STALTA.get(event["category"], DEFAULT_STALTA["regional_earthquake"])
    return {
        "filter_band": tuple(defaults["filter_band"]),
        "sta": float(sp.get("sta", defaults["sta"])),
        "lta": float(sp.get("lta", defaults["lta"])),
        "on": float(sp.get("on_thresh", defaults["on"])),
        "off": float(sp.get("off_thresh", defaults["off"])),
    }


def _input_for_real(event: dict) -> CanonicalPlotInput:
    """Fetch waveforms via FDSN and run the canonical recipe."""
    from obspy import UTCDateTime  # local import — fail late
    from obspy.clients.fdsn import Client

    station = event["recommended_stations"][0]
    t0 = UTCDateTime(event["origin_time"])
    half_s = event["suggested_window_min"] * 60.0 / 2
    p = _params_for(event)

    client = Client("IRIS")
    st = client.get_waveforms(
        network=station["network"],
        station=station["station"],
        location=station["location"],
        channel=station["channel"],
        starttime=t0 - half_s,
        endtime=t0 + half_s,
        attach_response=False,
    )
    return stream_to_canonical_input(
        st,
        event_label=event["label"],
        sta_s=p["sta"],
        lta_s=p["lta"],
        on_thresh=p["on"],
        off_thresh=p["off"],
        filter_band=p["filter_band"],
    )


def _input_for_synth(event: dict) -> CanonicalPlotInput:
    station = event["recommended_stations"][0]
    p = _params_for(event)
    return synthetic_canonical_input(
        event_id=event["id"],
        station_label=f"{station['network']}.{station['station']}",
        event_label=event["label"],
        duration_s=event["suggested_window_min"] * 60.0,
        sampling_rate_hz=40.0,
        sta_s=p["sta"],
        lta_s=p["lta"],
        on_thresh=p["on"],
        off_thresh=p["off"],
        has_event=bool(event.get("expected_detection", True)),
        seed=42,
    )


def _resolve_output_dir(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return Path(args.output_dir).expanduser().resolve()
    if args.private:
        env = os.environ.get("FM_STALTA_GOLDEN_DIR")
        if not env:
            raise SystemExit(
                "FM_STALTA_GOLDEN_DIR must be set when --private is used "
                "(or pass --output-dir explicitly)"
            )
        return Path(env).expanduser().resolve()
    return PUBLIC_DIR.resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", default=DEFAULT_EVENTS, type=Path)
    parser.add_argument("--only", nargs="*", default=None,
                        help="Only generate goldens for these event ids")
    parser.add_argument("--output-dir", default=None,
                        help="Output directory; overrides --private and the default public dir")
    parser.add_argument("--private", action="store_true",
                        help="Write to $FM_STALTA_GOLDEN_DIR (gitignored, for VERIFY events)")
    parser.add_argument("--synth", action="store_true",
                        help="Use deterministic synthetic data instead of FDSN (no network needed)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing PNGs without asking")
    args = parser.parse_args(argv)

    out_dir = _resolve_output_dir(args)
    out_dir.mkdir(parents=True, exist_ok=True)

    events = _load_events(args.events)
    if args.only:
        events = [e for e in events if e["id"] in set(args.only)]
        if not events:
            print(f"No events matched --only {args.only!r}", file=sys.stderr)
            return 2

    written: list[Path] = []
    for ev in events:
        out_path = out_dir / f"{ev['id']}.png"
        if out_path.exists() and not args.force:
            print(f"SKIP {out_path} (exists; pass --force to regenerate)")
            continue

        print(f"Building {ev['id']:<32} → {out_path}")
        try:
            arr = _input_for_synth(ev) if args.synth else _input_for_real(ev)
        except Exception as exc:  # pragma: no cover - depends on network
            print(f"  FDSN/recipe error for {ev['id']}: {exc}", file=sys.stderr)
            if args.synth:
                raise
            print(f"  Falling back to --synth for {ev['id']}", file=sys.stderr)
            arr = _input_for_synth(ev)

        render_canonical_plot(arr, out_path)
        written.append(out_path)

    print(f"\nDone. Wrote {len(written)} goldens to {out_dir}")
    if args.synth:
        print(
            "WARNING: synthetic goldens are placeholders. Regenerate with real "
            "FDSN data on a host with network access before publishing benchmark numbers.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
