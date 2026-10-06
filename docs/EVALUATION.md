# Evaluation

> **What these numbers measure:** detection of **injected faults** on a seeded dataset built from 30 real published carbon projects. They do **not** measure real-world fraud prevalence, and the "legitimate" projects are only *presumed* legitimate.

Reproduce:

```bash
cd backend
python -m scripts.evaluate find-boxes   # once
python -m scripts.evaluate run          # writes data/eval/results.json
```

All evidence is cached in `data/cache/evidence/` (`ev2`), so results reproduce exactly.

## Review correction: rules-v2 → rules-v3

2026-10-06: corrected area inputs to sum independently oriented polygon parts and
subtract holes regardless of source winding. This follows geometry semantics; no
threshold or deduction changed. Schema 1.0 hashes and satellite ev2 numbers are unchanged.
Both versions were run with `backend/.venv/Scripts/python.exe -m scripts.evaluate run`
from `backend/`, using only committed evidence. Metrics were unchanged:

| Metric | rules-v2 before | rules-v3 after |
|---|---|---|
| Recall | .716 (73/102) | .716 (73/102) |
| Precision | .973 | .973 |
| False alarms | 2/30 | 2/30 |
| Inflation detected | 3/30 | 3/30 |

The unchanged evaluation does not negate the bug: injected geometry uses the seed's
ordinary winding. Mixed orientation and hole regressions independently demonstrate it.

## Setup

**Negatives (presumed legitimate, n = 30):** the real seed claims as published. Each uses its published boundary (Karnik et al. 2024) and the credits it actually issued for its latest vintage (OffsetsDB). Overlaps are checked against the other 29.

**Positives (injected faults, n = 102):**

| Fault | n | How it is injected |
|---|---|---|
| DUPLICATE | 30 | Same boundary, new project ID, same vintage. |
| SHIFTED | 30 | Boundary translated east by 30% of its own width, same vintage. |
| INFLATED | 30 | Claimed credits × 5 on the same land. |
| RELOCATED | 12 | A real avoided-deforestation claim moved onto a 0.05° box in the Rondônia frontier where Hansen records clearing in the vintage year. It keeps its credits per hectare. Boxes were chosen deterministically, 3 per loss-severity band (1–2%, 2–5%, 5–15%, >15% of year-2000 forest lost in one year), at the band's 25th/50th/75th percentile so they don't cluster at the severe edge. |

**Detection rule:** the claim is blocked by the overlap check, *or* its integrity score is below 60, the contract's issuance threshold. Both mean "no credits issue".

**Baseline (uniqueness only):** what a registry with an overlap check but no evidence layer would catch.

**Thresholds were frozen** (`rules-v2`) before this evaluation ran, and were not tuned to it.

**No ML model.** With 30 base projects, a learned model would mostly memorise the injection recipe. Per the handoff's cut order we ship the transparent rule baseline, and we say so.

## Results

| | ClearCredit (`rules-v2`) | Baseline (uniqueness only) |
|---|---|---|
| Recall, all faults | **0.716** (73/102) | 0.578 (59/102) |
| Precision | 0.973 | 1.000 |
| False-alarm rate on real projects | **0.067** (2/30) | 0.000 (0/30) |

### Per fault

| Fault | ClearCredit | Baseline |
|---|---|---|
| DUPLICATE | 30/30 | 30/30 |
| SHIFTED | 29/30 | 29/30 |
| INFLATED | **3/30** | 0/30 |
| RELOCATED | **11/12** | 0/12 |

### RELOCATED by loss severity

| One-year forest loss (share of 2000 forest) | ClearCredit | Baseline |
|---|---|---|
| 1–2% | 2/3 | 0/3 |
| 2–5% | 3/3 | 0/3 |
| 5–15% | 3/3 | 0/3 |
| >15% | 3/3 | 0/3 |

The evidence layer is what catches relocated claims. Every one of the 11 detections fires `FOREST_LOSS_HIGH`, so detection comes from the satellite signal, not from the credit numbers carried over from the base project.

The 1–2% band does better than the rule's 2% line suggests. Boxes were *selected* by loss as a share of forest in **2000**, but the scorer divides by forest **remaining** before the vintage, and these frontier boxes had already lost much of their forest. The miss (RELOC-0, 1.2%) scored 80 with only `FOREST_LOSS_MODERATE`. **Light clearing below ~2% of remaining forest per year passes.** That is a known limitation, and we did not lower the threshold after seeing it.

## What it misses, and why

- **Moderate credit inflation (27/30 missed).** The per-hectare plausibility ranges are broad (avoided deforestation flags above 15 t/ha/yr and is "implausible" above 30). Real projects here issue roughly 1–17 t/ha/yr, so ×5 often stays inside the range or costs only 10 points. Catching it needs project-specific baselines (methodology, reference region, past issuance), which we do not have. *This is the weakest part of the scorer.*
- **One shifted copy (VCS1085), which is really a flaw in the fault recipe.** VCS1085 is a fragmented multi-part boundary. Shifting it by 30% of its width moves every part into the gaps between the original's parts. The shifted copy shares **no land** with the original (< 0.01 ha) and **0** H3 cells, so nothing is counted twice. It is scored as a miss to keep the recipe fixed, but no checker should block it.

## False alarms on real projects (2/30)

These are **not findings about the projects.** They show where the rules are wrong or where human review is needed.

| Project | Score | Reasons | Interpretation |
|---|---|---|---|
| VCS562 (Kasigau Corridor, Kenya) | 50 | `LITTLE_FOREST`, `NDVI_DECLINING` | Dryland woodland. The 30% canopy threshold assumes closed tropical forest, so "forest cover in 2000" comes out as 4 ha. The rule is wrong for this ecosystem. A fix would be biome-specific canopy thresholds; we have not tuned it here. |
| VCS812 (Bull Run, Belize) | 30 | `FOREST_LOSS_HIGH`, `CREDITS_HIGH` | Hansen records loss in several years (2006: 128 ha, 2009: 149 ha, 2010 vintage: 78 ha, 2011: 272 ha). Hansen "loss" counts **any** stand-replacing disturbance, whether clearing, fire, storms or pests, so this data cannot attribute a cause. Flagged for human review, not a conclusion. |

## Limitations of this evaluation

- Faults are synthetic transformations; real double counting and inflated baselines are subtler and adversarial.
- 30 base projects across 15 countries is a small sample; the confidence intervals are wide.
- Relocation boxes all come from one region (Rondônia, Brazil) and one dataset (Hansen GFC), so this tests the loss rule, not generalisation across biomes.
- SHIFTED and INFLATED reuse the base project's evidence (the injected property is geometry or credits, not land cover).
- The worked example SYN-05 (`data/synthetic/`) is a standalone synthetic placement and is **excluded** from these metrics.
