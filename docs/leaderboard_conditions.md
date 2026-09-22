# Leaderboard Conditions

The Repère leaderboard should compare not only model IDs, but also the agent configuration used to produce each result. A domain skill changes what the agent knows and how it approaches the task, so it must be visible in the leaderboard metadata.

## Condition fields

Each result JSON may include these optional fields:

| Field | Meaning | Example |
|---|---|---|
| `agent_condition` | Human-readable condition shown on the leaderboard. | `generic-coding-agent` or `SeismoDataAgent+skill-v0.1-draft` |
| `skill_name` | Skill identifier if a skill was active. | `seismo-data-agent` |
| `skill_version` | Version string for the skill instructions. | `v0.1-draft` |

If the fields are missing, the exporter treats the row as `generic-coding-agent`.

## Why this matters

A raw coding agent and a seismology-guided agent are different experimental conditions. The skill may improve correctness by reminding the model to:

- use ObsPy FDSN clients;
- preprocess traces before STA/LTA;
- query regional or global catalogs;
- calculate TauP travel-time plausibility;
- avoid hallucinating catalog matches or earthquakes in quiet windows.

Those improvements are the point of the skill, but they should not be hidden inside a single model score.

## Example result payload

```json
{
  "model_id": "example-model",
  "agent_condition": "SeismoDataAgent+skill-v0.1-draft",
  "skill_name": "seismo-data-agent",
  "skill_version": "v0.1-draft",
  "suite": "sta_lta.full_private_v0",
  "score": 0.82,
  "cost_usd": 0.14,
  "n_completed": 30,
  "n_total": 30
}
```

The leaderboard exporter will rank by score, then lower cost, while preserving the condition fields for public display.

## Recommended conditions for early experiments

1. `generic-coding-agent`
   - No seismology skill loaded.
   - Measures baseline agent capability.

2. `SeismoDataAgent+skill-v0.1-draft`
   - Uses `.github/skills/seismo-data-agent/SKILL.md`.
   - Measures the effect of domain workflow guidance.

3. Future versions such as `SeismoDataAgent+skill-v0.2`
   - Use only when the skill content changes materially.
   - Keep older skill versions available or archived so historical results remain interpretable.

Do not include private golden labels or event answers in the skill file or public condition metadata.
