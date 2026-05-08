# Seismic report templates

## Regional/local positive

> An STA/LTA trigger was recorded on `<NETWORK>.<STATION>..<CHANNEL>` at
> `<UTC TIME>`, consistent with `<CATALOG>` catalog event `<id>` (M`<mag>`,
> depth `<depth>` km, `<event_label>`). Detection used STA=`<sta>` s,
> LTA=`<lta>` s, on=`<on>`, off=`<off>`.

## Teleseismic positive

> A long-period STA/LTA trigger was recorded on `<NETWORK>.<STATION>..<CHANNEL>`
> at `<UTC TIME>`. The trigger time is consistent with the predicted
> P-arrival from `<EVENT>` (`<CATALOG>` `<id>`, M`<mag>`, depth `<depth>` km)
> at `<distance>°` epicentral distance under the iasp91 velocity model.
> Detection used STA=`<sta>` s, LTA=`<lta>` s, on=`<on>`, off=`<off>`.

## Anthropogenic (quarry blast) positive

> An STA/LTA trigger consistent with a quarry blast was recorded on
> `<NETWORK>.<STATION>..<CHANNEL>` at `<UTC TIME>`. The PNSN catalog flags
> this event as `event_type=quarry blast` (catalog id `<id>`). It is not a
> tectonic earthquake. Detection used STA=`<sta>` s, LTA=`<lta>` s,
> on=`<on>`, off=`<off>`.

## Negative window

> No events detected above the STA/LTA threshold (on=`<on>`, off=`<off>`) on
> `<NETWORK>.<STATION>..<CHANNEL>` during the `<duration>` window starting
> `<UTC TIME>`. Maximum value of the characteristic function: `<max_cft>`.

## Calibration notes

- Time stamps must be UTC and ISO-8601. No local time, ever.
- Round magnitudes to 0.1, depths to 0.1 km, distances to 0.1°.
- Use the same precision as the catalog you are citing; do not over-specify.
