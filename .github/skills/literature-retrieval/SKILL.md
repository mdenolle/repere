---
name: literature-retrieval
version: v0.1
task_kind: retrieval
description: >-
  Domain skill for ranking scientific papers against a research question. Use
  when the agent must decide which of several same-field candidate papers
  actually answers a question. Teaches the failure mode that dominates this task:
  ranking by shared vocabulary rather than by shared contribution.
validators:
  - "returns_strict_json_array"
  - "ranks_every_candidate_once"
---

# Ranking papers against a research question

The candidates are all from the same field. They will *all* mention seismic
waves, earthquakes, inversion, noise. **Vocabulary overlap therefore carries
almost no information, and ranking by it is the single most common way to get
this wrong.** The right paper is the one whose *contribution* matches the
question, not the one that repeats the most words from it.

## 1. Decompose the question into three parts

Nearly every research question in this field factorises:

| Part | Question | Example |
|---|---|---|
| **Object** | what is being studied? | the Santorini swarm; a lunar detector site; porosity |
| **Method** | how? | Fourier neural operators; acoustic metamaterials; a CNN |
| **Setting / claim** | under what conditions, and what is asserted? | low SNR; a homogeneous medium; *precedes* stronger events |

A candidate must match **all three**. A paper with the right method on the wrong
object is a distractor, and it is exactly the distractor that shares the most
words with the question.

## 2. Read the abstract for the contribution, not the topic

Ask of each candidate: *what does this paper claim to have done?* Then ask
whether that is what the question describes. A paper that merely *uses* a
technique is not the paper that *proposes* it. A paper that *reviews* a problem
is not the paper that *solves* it.

Pay attention to verbs: **propose, develop, present, demonstrate, report** mark
the contribution. Background sentences do not.

## 3. Discriminating cues that usually settle it

- **A named object** (Santorini, Turkey, Australia, the Moon) is decisive. If the
  question names one, the answer almost certainly names the same one.
- **A named method** (Fourier neural operators, acoustic metamaterials, spectral
  decomposition) is nearly as decisive.
- **A stated relationship** ("changes *precede* stronger earthquakes",
  "*accelerates* uncertainty quantification") must appear as a claim, not as
  motivation.
- **Scale and target** distinguish otherwise-similar papers: small-magnitude
  detection is not the same task as real-time monitoring of an aftershock
  sequence, even though both are deep learning on seismic phases.

## 4. Rank, do not just pick

You are asked for a full ranking, and partial credit depends on where the
correct paper lands. After choosing your first, place the remainder by how many
of the three parts (object / method / setting) they still match. A candidate
sharing the object should outrank one sharing only generic vocabulary.

## 5. Output contract

Return **only** a JSON array of the candidate ids, best first. Include **every**
candidate exactly once, no duplicates, no omissions, no prose, no code fence:

```
["2203.14386v1", "1810.08517v1", "2204.02870v1", ...]
```

Any commentary before or after the array is a failure of the task, not a bonus.
