"""Croissant metadata for released Repère datasets.

Three documents describe one release:

- ``croissant.json`` -- the dataset, in Croissant 1.1 with the Responsible AI
  (RAI) extension, plus GeoCroissant 1.0 properties when the release has a
  place and a time (``geo`` in ``datasets/releases.yaml``). One FileObject and
  one RecordSet per suite file, a Split RecordSet, sha256 on every file.
- ``tasks.jsonld`` -- one Croissant Tasks ``TaskProblem`` per suite: the
  dataset as input, an OutputSpec for what the model must return, an
  ImplementationSpec for the agent under test, and an EvaluationSpec naming the
  scorer. Croissant Tasks is experimental upstream (mlcommons/croissant
  ``tasks/``); its SHACL shapes are what we validate against.
- the dataset card (``README.md``), written by ``scripts/build_hf_release.py``.

Specs, as read on 2026-10-28 from mlcommons/croissant at ec24358:
``docs/croissant-spec-1.1.md``, ``docs/croissant-rai-spec.md``,
``docs/croissant-geo-spec.md`` and ``tasks/croissant-tasks.ttl``.

Nothing here imports mlcroissant; the output is plain JSON. The tests validate
it with mlcroissant and pyshacl when those are installed.
"""

from __future__ import annotations

from typing import Any

CROISSANT_1_1 = "http://mlcommons.org/croissant/1.1"
GEOCROISSANT_1_0 = "http://mlcommons.org/croissant/geo/1.0"

CONTEXT: dict[str, Any] = {
    "@language": "en",
    "@vocab": "https://schema.org/",
    "arrayShape": "cr:arrayShape",
    "citeAs": "cr:citeAs",
    "column": "cr:column",
    "conformsTo": "dct:conformsTo",
    "containedIn": "cr:containedIn",
    "cr": "http://mlcommons.org/croissant/",
    "rai": "http://mlcommons.org/croissant/RAI/",
    "geocr": "http://mlcommons.org/croissant/geo/",
    "data": {"@id": "cr:data", "@type": "@json"},
    "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
    "dct": "http://purl.org/dc/terms/",
    "equivalentProperty": "cr:equivalentProperty",
    "examples": {"@id": "cr:examples", "@type": "@json"},
    "extract": "cr:extract",
    "field": "cr:field",
    "fileProperty": "cr:fileProperty",
    "fileObject": "cr:fileObject",
    "fileSet": "cr:fileSet",
    "format": "cr:format",
    "includes": "cr:includes",
    "isArray": "cr:isArray",
    "isLiveDataset": "cr:isLiveDataset",
    "jsonPath": "cr:jsonPath",
    "key": "cr:key",
    "md5": "cr:md5",
    "parentField": "cr:parentField",
    "path": "cr:path",
    "recordSet": "cr:recordSet",
    "references": "cr:references",
    "regex": "cr:regex",
    "repeated": "cr:repeated",
    "replace": "cr:replace",
    "samplingRate": "cr:samplingRate",
    "sc": "https://schema.org/",
    "separator": "cr:separator",
    "source": "cr:source",
    "subField": "cr:subField",
    "transform": "cr:transform",
}

# BenchmarkRow columns exposed as Croissant fields. The scalar columns are
# text; `gold`, `scorer_spec` and `metadata` are JSON values whose shape differs
# between suites, so their sub-fields are derived from the rows themselves.
SCALAR_FIELDS: list[tuple[str, str]] = [
    ("id", "Stable row id, <dataset_id>/<suite_id>/<case_id>."),
    ("suite_id", "Task family within the dataset."),
    ("task_kind", "Repère task kind (extraction, code_generation, ...)."),
    ("split", "Partition; only 'validation' is released."),
    ("prompt", "The prompt given to the model or agent."),
]
OBJECT_FIELDS: list[tuple[str, str]] = [
    ("gold", "Reference answer."),
    ("scorer_spec", "Declarative scorer, rebuilt with make_scorer_from_spec(scorer_spec)."),
    ("metadata", "Case metadata."),
]


def _scalar_type(values: list[Any]) -> str | None:
    """Croissant dataType for a list of JSON scalars (None if not uniform)."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    if all(isinstance(v, bool) for v in vals):
        return "sc:Boolean"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
        return "sc:Integer"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return "sc:Float"
    if all(isinstance(v, str) for v in vals):
        return "sc:Text"
    return None


def _value_field(
    field_id: str, name: str, values: list[Any], source: dict[str, Any], path: str | None
) -> dict[str, Any] | None:
    """A Croissant Field for one JSON value position, recursing into objects.

    ``path`` is the jsonPath below the extracted column (None for the column
    itself). Returns None when the values have no single representable type.
    """
    present = [v for v in values if v is not None]
    if not present:
        return None
    src = dict(source)
    if path:
        src["transform"] = {"jsonPath": path}
    if all(isinstance(v, dict) for v in present):
        keys = sorted({k for v in present for k in v})
        subs = []
        for k in keys:
            sub = _value_field(
                f"{field_id}/{k}",
                k,
                [v.get(k) for v in present],
                source,
                f"{path}.{k}" if path else k,
            )
            if sub is not None:
                subs.append(sub)
        if not subs:
            return None
        return {"@type": "cr:Field", "@id": field_id, "name": name, "subField": subs}
    if all(isinstance(v, list) for v in present):
        dtype = _scalar_type([x for v in present for x in v])
        if dtype is None and all(len(v) == 0 for v in present):
            dtype = "sc:Float"
        if dtype is None:
            return None
        return {
            "@type": "cr:Field",
            "@id": field_id,
            "name": name,
            "dataType": dtype,
            "isArray": True,
            "arrayShape": "-1",
            "source": src,
        }
    dtype = _scalar_type(present)
    if dtype is None:
        return None
    return {"@type": "cr:Field", "@id": field_id, "name": name, "dataType": dtype, "source": src}


def _file_object(f: dict[str, Any], base_url: str) -> dict[str, Any]:
    return {
        "@type": "cr:FileObject",
        "@id": f["path"],
        "name": f["path"],
        "description": f["description"],
        "contentUrl": base_url + f["path"],
        "encodingFormat": f["encoding"],
        "sha256": f["sha256"],
    }


def _row_record_set(f: dict[str, Any]) -> dict[str, Any]:
    rs_id = f["suite_id"]
    rows = f["rows_data"]
    fields = []
    for name, desc in SCALAR_FIELDS:
        field: dict[str, Any] = {
            "@type": "cr:Field",
            "@id": f"{rs_id}/{name}",
            "name": name,
            "description": desc,
            "dataType": "sc:Text",
            "source": {"fileObject": {"@id": f["path"]}, "extract": {"column": name}},
        }
        if name == "split":
            field["references"] = {"field": {"@id": "splits/split_name"}}
        fields.append(field)
    for name, desc in OBJECT_FIELDS:
        source = {"fileObject": {"@id": f["path"]}, "extract": {"column": name}}
        field = _value_field(f"{rs_id}/{name}", name, [r.get(name) for r in rows], source, None)
        if field is not None:
            field["description"] = desc
            fields.append(field)
    return {
        "@type": "cr:RecordSet",
        "@id": rs_id,
        "name": rs_id,
        "description": f.get("record_description", f["description"]),
        "key": {"@id": f"{rs_id}/id"},
        "field": fields,
    }


def _split_record_set(splits: list[str]) -> dict[str, Any]:
    return {
        "@type": "cr:RecordSet",
        "@id": "splits",
        "name": "splits",
        "description": "Partitions present in this release.",
        "dataType": "cr:Split",
        "key": {"@id": "splits/split_name"},
        "field": [
            {
                "@type": "cr:Field",
                "@id": "splits/split_name",
                "name": "split_name",
                "description": "Name of the partition.",
                "dataType": "sc:Text",
            }
        ],
        "data": [{"splits/split_name": s} for s in splits],
    }


def _geo_properties(geo: dict[str, Any]) -> dict[str, Any]:
    """schema.org spatial/temporal coverage plus GeoCroissant 1.0 terms."""
    out: dict[str, Any] = {
        "spatialCoverage": {
            "@type": "Place",
            "name": geo["station"],
            "geo": {
                "@type": "GeoCoordinates",
                "latitude": geo["latitude"],
                "longitude": geo["longitude"],
                "elevation": geo.get("elevation_m"),
            },
        },
        "temporalCoverage": geo["temporal_coverage"],
        "geocr:coordinateReferenceSystem": geo.get("crs", "EPSG:4326"),
    }
    if geo.get("sampling_rate_hz"):
        out["geocr:temporalResolution"] = {
            "@type": "QuantitativeValue",
            "value": 1.0 / float(geo["sampling_rate_hz"]),
            "unitText": "s",
        }
    return out


def dataset_metadata(
    release: dict[str, Any],
    files: list[dict[str, Any]],
    *,
    url: str,
    base_url: str,
    cite_as: str,
    date_published: str,
    creator: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the Croissant 1.1 (+RAI, +GeoCroissant) JSON-LD for one release.

    ``files`` entries carry ``path``, ``sha256``, ``encoding``, ``description``
    and, for row files, ``suite_id``. ``base_url`` is prefixed to each path to
    form ``contentUrl`` (empty string for paths relative to this file).
    """
    geo = release.get("geo")
    conforms: Any = [CROISSANT_1_1, GEOCROISSANT_1_0] if geo else CROISSANT_1_1
    license_url = release.get("license_url")
    md: dict[str, Any] = {
        "@context": CONTEXT,
        "@type": "sc:Dataset",
        "name": release["hf_repo"].split("/")[-1],
        "alternateName": release["pretty_name"],
        "description": " ".join(release["description"].split()),
        "conformsTo": conforms,
        "citeAs": cite_as,
        "license": license_url,
        "url": url,
        "version": release["version"].removeprefix("v"),
        "datePublished": date_published,
        "creator": creator,
        "publisher": {"@type": "Organization", "name": "gaia-hazlab", "url": "https://huggingface.co/gaia-hazlab"},
        "keywords": release.get("keywords", []),
        "isAccessibleForFree": True,
    }
    if release.get("license_note"):
        md["usageInfo"] = " ".join(release["license_note"].split())
    based_on = []
    dep = release.get("depends_on")
    if dep:
        based_on.append(
            {
                "@type": "SoftwareSourceCode",
                "name": dep["name"],
                "codeRepository": dep["url"],
                "version": f"{dep['version']} ({dep['commit']})",
            }
        )
    for c in release.get("cite_also", []):
        doi = c[c.find("https://doi.org/"):].split()[0] if "https://doi.org/" in c else None
        based_on.append({"@type": "Dataset", "name": c, **({"identifier": doi} if doi else {})})
    if based_on:
        md["isBasedOn"] = based_on
    if geo:
        md.update(_geo_properties(geo))
    for key, value in (release.get("rai") or {}).items():
        md[f"rai:{key}"] = " ".join(value.split()) if isinstance(value, str) else value

    md["distribution"] = [_file_object(f, base_url) for f in files]
    row_files = [f for f in files if f.get("suite_id")]
    md["recordSet"] = [_split_record_set(["validation"])] + [_row_record_set(f) for f in row_files]
    return md


def task_problems(
    release: dict[str, Any],
    suites: list[dict[str, Any]],
    *,
    url: str,
    repere_version: str,
) -> dict[str, Any]:
    """One Croissant Tasks ``TaskProblem`` per suite, as a JSON-LD graph.

    ``suites`` entries carry ``suite_id``, ``task_kind``, ``scorer`` (name),
    ``output`` and ``evaluation`` (text from ``datasets/releases.yaml``).
    """
    graph = []
    for s in suites:
        tid = f"{url}#task-{s['suite_id']}"
        graph.append(
            {
                "@type": "croissant:TaskProblem",
                "@id": tid,
                "dct:conformsTo": CROISSANT_1_1,
                "schema:name": f"{release['hf_repo'].split('/')[-1]} / {s['suite_id']}",
                "schema:description": (
                    f"Repère {s['task_kind']} task. Each row of record set "
                    f"'{s['suite_id']}' is one problem instance: give the prompt to "
                    "the system under test, then score its answer with the row's scorer_spec."
                ),
                "croissant:input": {
                    "@type": "schema:Dataset",
                    "@id": url,
                    "dct:conformsTo": CROISSANT_1_1,
                    "schema:name": release["hf_repo"],
                },
                "croissant:output": {
                    "@type": "croissant:OutputSpec",
                    "@id": f"{tid}/output",
                    "schema:description": " ".join(s["output"].split()),
                },
                "croissant:implementation": {
                    "@type": "croissant:ImplementationSpec",
                    "@id": f"{tid}/implementation",
                    "schema:description": (
                        "The model or agent under test. Repère runs it with and without "
                        "a domain skill file; tools, budget and model are recorded per run "
                        "in the leaderboard row."
                    ),
                },
                "croissant:execution": {
                    "@type": "croissant:ExecutionSpec",
                    "@id": f"{tid}/execution",
                    "schema:description": (
                        "Repeated runs per configuration (default 5, temperature 0.7); "
                        "report mean score with a bootstrap interval."
                    ),
                },
                "croissant:evaluation": {
                    "@type": "croissant:EvaluationSpec",
                    "@id": f"{tid}/evaluation",
                    "schema:name": s["scorer"],
                    "schema:description": " ".join(s["evaluation"].split()),
                    "schema:url": "https://github.com/mdenolle/repere",
                    "schema:version": repere_version,
                },
            }
        )
    return {
        "@context": {
            "croissant": "http://mlcommons.org/croissant/",
            "schema": "https://schema.org/",
            "dct": "http://purl.org/dc/terms/",
        },
        "@graph": graph,
    }
