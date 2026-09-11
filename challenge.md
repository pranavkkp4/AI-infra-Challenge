# The Dark Data PM Analyst Challenge: working brief

Run `aisa_challenge.ipynb` first. It loads the data and shows you where it gets hard.
This document covers the work.

---

## What you are given

A real Cityworks work-order export from a municipal Public Works and Facilities
department: water, sewer, streets, traffic, electric and buildings. Three CSV files
in `data/`.

| File | Rows | What it is |
|---|---|---|
| `WORKORDER.csv` | 37,778 | One row per job. 135 columns, 36 of them entirely empty |
| `WOENTITY.csv` | 867,448 | Which assets each job touched |
| `WOCOMMENT.csv` | 33,572 | What people wrote. This is the dark data |

Most of the corpus falls in 2008 to 2010, with a thin tail out to 2023.

### The schema in one block

```
WORKORDER                    one row per job
   |  WorkOrderId            join key, unique
   |
   +-- WOENTITY              1 to 14,232 assets per job
   |     WorkOrderId  -> WORKORDER.WorkOrderId
   |     EntityType + EntityUid = the asset key
   |
   +-- WOCOMMENT             0 or 1 notes per job
         WorkOrderId  -> WORKORDER.WorkOrderId
```

Three things that will bite you if you skip them:

- **`EntityUid` alone is not unique.** The same number means different things under
  different `EntityType` values. Key on both.
- **`ApplyToEntity` is not the asset.** It is the job template's intended class, and
  it often disagrees with what was actually attached. The asset comes from `WOENTITY`.
- **Joining through `WOENTITY` gives one row per job x asset.** Count rows on that
  frame and you are counting assets touched, not work done.

The columns worth keeping: `WorkOrderId`, `InitiateDate`, `Description`, `Shop`,
`AssetGroup`, `Priority`, `WOAddress`, `Location`, `Status`, `IsReactive`, `Text10`.

## What you must build

Per `problem.md`: a RAG pipeline over the work order text, an ALP library encoding
expert heuristics, a confidence scoring engine, and a dispatcher output. The
deliverable is a structured `PM_INSIGHT_REPORT` grounded in specific work orders.

---

## The dataset serves every scoring metric

| Metric | Points | What is in the data |
|---|---|---|
| **ALP Logic Depth** | 30 | Real trigger families are present in the note text, but they are municipal, not rotating-equipment. You have to find them. See below |
| **Architectural Integrity** | 30 | 33,459 notes to vectorize. They run from 1 to 3,172 characters, median 152 |
| **Explainability** | 20 | Every work order has an id, an asset, a site and a timestamp. Evidence can cite real records a manager can open |
| **Data Normalization** | 10 | Catch-all asset ids, free-text addresses, case-variant categories, template class disagreeing with attached asset. All real, all yours to handle |
| **Operational Impact** | 10 | 2,680 assets carry three or more work orders. Some of those sequences are a problem nobody joined up |

### The ALP triggers are not the ones in problem.md

`problem.md` gives four example phrases: "vibration within metrics", "rust/corrosion
on mount", "leaking but holding", "parts sticking/greasy". Those describe rotating
mechanical equipment.

**This corpus is water mains, sewer lines, meters, streetlights, signal cabinets,
pavement and building HVAC.** Those four phrases are almost absent from it. Measured
across all 33,572 notes: "leaking but holding" appears zero times, "vibration within
metrics" six times.

That is not a problem with the data. **Read the four rows in `problem.md` as the
shape of an ALP, not as a list to go find:**

```
observation the crew actually writes  ->  what it means  ->  what the agent should do
```

Your job is to fill that shape with triggers this corpus actually contains.

### A starting sample, not the answer

A crude substring count over the 33,572 notes turns up these families:

| Family | Notes | Share |
|---|---|---|
| meter problem | 5,926 | 17.7% |
| pothole / pavement | 4,511 | 13.4% |
| water leak / main break | 2,681 | 8.0% |
| low or no pressure | 1,529 | 4.6% |
| sewer stoppage / backup | 851 | 2.5% |
| no problem found | 837 | 2.5% |
| jetting / line cleaning | 722 | 2.2% |
| HVAC no cool / no heat | 712 | 2.1% |
| repeat / still broken | 682 | 2.0% |
| roots or grease in line | 559 | 1.7% |

**Treat this table as a hint, not a result.** It came from matching a handful of
substrings. It will have missed wordings, double-counted notes that mention two
things, and caught records that are not about a fault at all.

**Exercise, and it is worth the 30 points:** mine your own families out of the
corpus. Read a few hundred notes. Find how a crew actually says a thing, then build
the ALP against those wordings and justify them. An ALP that keys on "bearing wear"
will never fire here. One that keys on what is written might.

### Deduplication and crisis clusters

2,680 assets carry three or more work orders once inventory sweeps are excluded. A
time-gap rule splits those histories into 2,188 episodes of three or more jobs. Those
are your recurring failure patterns.

Key on `EntityType` plus `EntityUid`, never `EntityUid` alone.

---

## What the data gives you, and what you must infer

This is the part that decides whether your submission is analysis or lookup.

### Given

| | |
|---|---|
| `Comments` | The note. Dispatcher intake plus dated crew entries appended over time |
| `InitiateDate` | When the job was opened |
| `EntityType` + `EntityUid` | Which asset |
| `WOAddress` | Which site |
| `Shop` / `AssetGroup` | Which crew, which program |
| `Priority` | 1 to 6, set at intake |

### Not given, and deliberately so

| You must infer | Why it is not in the data |
|---|---|
| **Which work orders describe the same problem** | There is no incident id. You get 37,778 loose jobs |
| **What caused anything** | No note states a cause |
| **Which assets share a failure mode** | Two assets degrading the same way are never linked |
| **What the PM interval should become** | No record recommends a schedule change |
| **Whether a problem was ever resolved** | Read the last note and judge. There is no outcome field |

### The `CAUSAL_FACTOR` field

`problem.md` asks your `PM_INSIGHT_REPORT` to output:

```json
"CAUSAL_FACTOR": "Gasket leakage leads to lubrication contamination."
```

**Nothing in the dataset says that.** A crew records what they found and what they
did:

> Written: `A/C running but not producing cold air` ... `repaired A/C complete`
> ... four days later ... `A/C still not working - repair complete`
>
> Never written: `compressor undersized for the load after the 2007 retrofit`

Producing a causal factor means reading several notes about one asset, noticing that
a repair was called complete twice in a week, and concluding something no individual
record states. That inference is the assignment. It is not a gap in the data.

---

## Starting points by track

### AIML track

1. **Group the work orders.** Start with the asset key plus a time gap, then read the
   sequences and check whether your grouping holds up. Section 6 of the notebook does
   the minimum version.
2. **Build the ALP as a retrieval problem, not a regex.** Embed the trigger meanings
   and match semantically. The literal phrases barely appear; the meanings appear
   thousands of times.
3. **Ground the confidence score in measurement.** Section 5 produces an accuracy-by-
   similarity table. If accuracy rises with similarity, you have a real confidence
   signal and can set a threshold from the curve. Say what the score means and what
   you do below it.

### Construction RCA track

1. **Mine the wordings, do not invent them.** Pull the phrases the crews actually use
   out of the corpus, then write the ALP against those.
2. **Build the ALP around observations, not diagnoses.** The data contains symptoms
   and actions. An ALP keyed on a diagnosis will never fire.
3. **Use the HITL audit to find your failure modes.** Fifty insights read by hand will
   tell you more than any aggregate metric.

### Technical Writing track

1. **The reasoning narrative must cite work order ids.** Every claim traceable to a
   record a manager can open in Cityworks. Grounding is 20 of the 100 points.
2. **Write for a maintenance manager, not a data scientist.** "Accelerate PM from 6
   months to 3" is a decision. "Cosine similarity 0.83" is not.
3. **Document what the agent cannot do.** A report that states its own limits is more
   credible than one that does not.

---

## The notebook is your intro, not the solution

`aisa_challenge.ipynb` establishes that the data is workable and shows where the easy
part ends.

| Sections | What they give you |
|---|---|
| 1 | Load three CSVs, join them, see what is actually in there |
| 2 to 4 | Embed the notes, understand what the embedding represents and why cosine |
| 5 | A working classifier and a confidence curve you can reuse |
| 6 | Asset histories and episode segmentation. The core of the challenge |
| 7 | Sites with dense history |
| 8 to 10 | A minimal RAG loop, retrieval then generation |

Sections 1 to 8 run offline. Sections 9 and 10 need a free Google AI Studio key in a
`secrets.json` beside the notebook.

### One result to think about before you build

Section 5 asks whether the note text predicts which shop owns the job. Run it and look
at the confidence table, not the headline accuracy.

Vocabulary tells you what a note is about. It does not tell you whether a problem was
ever fixed, or whether two jobs six months apart are the same problem. **Spend your
LLM budget on the second kind of question.** A cheap embedding handles the first.

### A cheap baseline before anything complicated

Count work orders per asset. Assets with one job are routine; assets with six over a
year are not. If your sophisticated pipeline cannot beat counting, you have learned
something important.

---

## Traps

All of these are real and measured in this corpus.

| Trap | Reality |
|---|---|
| Counting rows on the joined frame | One job attaches up to 14,232 assets. Row counts describe assets touched, not work done. Deduplicate on `WorkOrderId` before counting anything about jobs |
| Treating every entity id as an asset | `CITYFACILITIES\|642` carries 3,766 work orders. It is a catch-all, not a thing that broke. So are `CITY_DEPTS\|MIS` and `CITY_DEPTS\|LEGAL` |
| Capping assets-per-job and calling it done | That cap does not catch the line above. One job touching many assets and one asset collecting many jobs are different problems |
| Building features on `Priority` | About 95% of work orders are priority `3`. It is a default nobody changed |
| Treating `Description` as a note | 376 distinct template titles across 37,778 jobs. A label, not evidence |
| Ignoring the dispatcher boilerplate | Most notes open with the same `From: Request ID:` header. It inflates every similarity score and can dominate the embedding space |
| Sending notes straight to an LLM | Employee names are inline as `By LAST, FIRST:`. That is PII |
| Trusting the dates | `InitiateDate` contains sentinels at 1970 and 2222. Filter before any time-series work |
| Assuming every note is maintenance | Many are meeting logs, training records and supply deliveries |
| Keying on `EntityUid` alone | Ids collide across entity types. Use `EntityType` plus `EntityUid` |
| Loading the full similarity matrix | `8n^2` bytes. 288 MB at 6,000 notes, 9 GB at 33,460. Sample or use an index |
| Keyword-matching the `problem.md` triggers | Those four phrases are effectively absent. The meanings, in this corpus's own words, are everywhere |
| Expecting a cause in the text | There is none. Inferring it across records is the assignment |

---

## Suggested checkpoints

| Stage | You should have |
|---|---|
| 1 | Data loaded and joined, work orders grouped into candidate episodes, grouping spot-checked by reading a few |
| 2 | Embeddings built, retrieval returning relevant records for a plain-language question |
| 3 | ALP v1 written from wordings mined out of the corpus, firing on real records |
| 4 | Confidence score defined and calibrated against something measured |
| 5 | A `PM_INSIGHT_REPORT` produced end to end, citing real work order ids |
| 6 | Fifty insights audited by hand, failure modes documented, ALP revised |

A team that reaches stage 3 with a defensible ALP is in better shape than one that
reaches stage 5 with a pipeline nobody can explain.
