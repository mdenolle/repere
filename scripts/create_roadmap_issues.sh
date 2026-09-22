#!/usr/bin/env bash
# Idempotent bootstrap for the Repère roadmap on GitHub Issues.
#
# Creates labels, milestones, and one issue per roadmap item from ROADMAP.md.
# Re-running is safe: existing labels/milestones are left alone, and existing
# issues are matched by title prefix `[Px.y]` and updated rather than duplicated.
#
# Requirements:
#   - `gh` CLI authenticated (`gh auth status`)
#   - `jq` (parses gh JSON output)
#   - `python3` (extracts roadmap sections and slugs anchors)
#   - Run from a clone of the repo (the script reads ROADMAP.md from the cwd)
#
# Usage:
#   bash scripts/create_roadmap_issues.sh                 # all items
#   bash scripts/create_roadmap_issues.sh --only P1.1 P1.3
#   bash scripts/create_roadmap_issues.sh --dry-run

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROADMAP="$REPO_ROOT/ROADMAP.md"

ONLY=()
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --only) shift; while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do ONLY+=("$1"); shift; done ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      grep -E '^# ' "$0" | sed 's/^# //'
      exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

command -v gh >/dev/null || { echo "gh CLI is required"; exit 1; }
command -v jq >/dev/null || { echo "jq is required (parses gh JSON output)"; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required (parses ROADMAP.md sections and slugs anchors)"; exit 1; }
[[ -f "$ROADMAP" ]] || { echo "ROADMAP.md not found at $ROADMAP"; exit 1; }

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
echo "Bootstrapping issues in $REPO"

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY: $*"
  else
    "$@"
  fi
}

# ----- Labels --------------------------------------------------------------
declare -a LABELS=(
  "astabench-alignment|7e57c2|Roadmap items aligning Repère with AstaBench standards"
  "area:framework|0366d6|Core framework: budget, telemetry, adapters, router"
  "area:skills|fbca04|Skills system, manifest, loader"
  "area:data|0e8a16|Truth set, fixtures, plot goldens"
  "area:scoring|d93f0b|Scorers, rubrics, judge integration"
  "area:site|1d76db|Static GitHub-Pages leaderboard"
  "area:agents|c5def5|Solver / agent baselines"
  "area:infra|bfdadc|CI, Docker, packaging"
  "effort:S|c2e0c6|≤1 day"
  "effort:M|fef2c0|2–5 days"
  "effort:L|f9d0c4|≥1 week"
)

for spec in "${LABELS[@]}"; do
  IFS='|' read -r name color desc <<< "$spec"
  if gh label list --limit 200 --json name -q '.[].name' | grep -qx "$name"; then
    echo "label exists: $name"
  else
    run gh label create "$name" --color "$color" --description "$desc"
  fi
done

# ----- Milestones ----------------------------------------------------------
declare -a MILESTONES=(
  "Phase 1 — Quick wins|AstaBench-alignment quick wins: metadata, splits, Pareto framing."
  "Phase 2 — Medium|InspectAI substrate, Docker sandbox, data versioning, agent baseline."
  "Phase 3 — Pivots|inspect_evals submission, larger truth set, hidden test split."
)

milestone_number() {
  local title="$1"
  gh api "repos/$REPO/milestones?state=all&per_page=100" --jq \
    ".[] | select(.title==\"$title\") | .number" | head -n1
}

for spec in "${MILESTONES[@]}"; do
  IFS='|' read -r title desc <<< "$spec"
  num=$(milestone_number "$title")
  if [[ -n "$num" ]]; then
    echo "milestone exists: $title (#$num)"
  else
    run gh api "repos/$REPO/milestones" -f title="$title" -f description="$desc" >/dev/null
    echo "milestone created: $title"
  fi
done

# ----- Issues from ROADMAP.md ---------------------------------------------
# Each issue is keyed by `## Px.y · Title`. Body is the section between that
# heading and the next `## ` heading.

py_extract() {
  python3 - "$ROADMAP" "$@" <<'PY'
import re, sys, json
roadmap_path = sys.argv[1]
text = open(roadmap_path).read()
sections = re.split(r"^## (?=P\d+\.\d+ · )", text, flags=re.MULTILINE)


def gh_slug(heading: str) -> str:
    """Mirror GitHub's heading-anchor rule: lowercase, drop punctuation
    (including '.', backticks, '·'), whitespace -> '-', collapse runs."""
    s = heading.lower()
    # Keep word chars (letters, digits, underscore), whitespace, and '-'; drop the rest.
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


items = []
for sec in sections[1:]:
    lines = sec.splitlines()
    head = lines[0].strip()
    m = re.match(r"^(P\d+\.\d+) · (.+)$", head)
    if not m:
        continue
    pid, title = m.group(1), m.group(2).strip()
    body = "\n".join(lines[1:]).strip()
    if pid.startswith("P1."):
        milestone = "Phase 1 — Quick wins"
    elif pid.startswith("P2."):
        milestone = "Phase 2 — Medium"
    elif pid.startswith("P3."):
        milestone = "Phase 3 — Pivots"
    else:
        milestone = ""
    # Extract Effort heuristically (look for `Effort` line).
    effort_match = re.search(r"Effort\*\*\s*([SML])", body)
    effort = effort_match.group(1) if effort_match else "M"
    # GitHub-compatible anchor for the section heading exactly as rendered.
    anchor = gh_slug(f"{pid} · {title}")
    items.append({
        "id": pid, "title": title, "body": body,
        "milestone": milestone, "effort": effort,
        "anchor": anchor,
    })
print(json.dumps(items))
PY
}

ITEMS_JSON=$(py_extract)

select_item() {
  local id="$1"
  if [[ "${#ONLY[@]}" -eq 0 ]]; then
    return 0
  fi
  for sel in "${ONLY[@]}"; do
    [[ "$sel" == "$id" ]] && return 0
  done
  return 1
}

issue_number_for_prefix() {
  local prefix="$1"
  gh issue list --search "in:title \"$prefix\"" --state all --limit 50 \
    --json number,title \
    --jq ".[] | select(.title | startswith(\"$prefix\")) | .number" | head -n1
}

count=$(jq 'length' <<< "$ITEMS_JSON")
echo "$count items in roadmap; filtering to selection: ${ONLY[*]:-<all>}"

for i in $(seq 0 $((count-1))); do
  pid=$(jq -r ".[$i].id" <<< "$ITEMS_JSON")
  title=$(jq -r ".[$i].title" <<< "$ITEMS_JSON")
  body=$(jq -r ".[$i].body" <<< "$ITEMS_JSON")
  milestone=$(jq -r ".[$i].milestone" <<< "$ITEMS_JSON")
  effort=$(jq -r ".[$i].effort" <<< "$ITEMS_JSON")
  anchor=$(jq -r ".[$i].anchor" <<< "$ITEMS_JSON")

  if ! select_item "$pid"; then
    continue
  fi

  full_title="[$pid] $title"
  prefix="[$pid]"

  body_with_link=$(printf "%s\n\n---\n_Source: [ROADMAP.md](../blob/main/ROADMAP.md#%s)_\n" \
    "$body" "$anchor")

  existing=$(issue_number_for_prefix "$prefix" || true)
  if [[ -n "$existing" ]]; then
    echo "issue exists for $pid: #$existing → updating body"
    run gh issue edit "$existing" \
      --body "$body_with_link" \
      --add-label "astabench-alignment,effort:$effort" \
      --milestone "$milestone" >/dev/null
  else
    echo "creating issue for $pid: $full_title"
    run gh issue create \
      --title "$full_title" \
      --body "$body_with_link" \
      --label "astabench-alignment,effort:$effort" \
      --milestone "$milestone" >/dev/null
  fi
done

echo "Done. View issues at: https://github.com/$REPO/issues?q=label%3Aastabench-alignment"
