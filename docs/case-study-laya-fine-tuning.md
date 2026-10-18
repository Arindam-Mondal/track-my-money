# Case study: teaching a small local model to read Indian bank statements

**Project:** track-my-money, a personal-finance app that imports bank statement PDFs.
**Question:** how do we put each transaction into a category (Food & Dining, House Rent, SIP, …)
**without sending people's bank data to a cloud AI**?
**Status:** fine-tuning prepared and verified; results pending the first Kaggle run.

---

## 1. The problem

A bank narration is a short, cryptic string:

```text
UPI/412345678/SWIGGY/swiggy@icici            -> Food & Dining
NACH-MUT-DR/BSE STAR MF/SIP 4567             -> Mutual Fund / SIP
29325130CARDAXIS CC 057578                   -> Credit Card Payment
Int.Pd:01-04-2026 to 30-06-2026              -> Interest
```

To show "where does my money go", every transaction needs one category out of 32 (23 for money out,
9 for money in). There are hundreds of transactions per statement, so this must be automatic.

**Constraints**

- **Privacy.** Narrations contain names, UPI IDs and account numbers. We wanted the categoriser
  to run **locally**.
- **Hardware.** The development laptop has 24 GB RAM, an Intel UHD 620 and **no NVIDIA GPU**.
- **Cost.** Free or near-free.

## 2. What we tried, and what we measured

We used one fixed test from the start: **18 typical narrations with known categories**, the same
for every option.

| Option | Where it runs | Correct (of 18) | Time per transaction |
|---|---|---|---|
| **Jev** (TypeSafe, hosted) | Cloud | **18** | 0.4 s |
| **Laya** base, one choice among 23 | Laptop CPU | 7–10 | 1.1–2.4 s |
| Laya base, two-step (group, then category) | Laptop CPU | 4–6 | 1.3–3.6 s |
| **Clef / Clef-Flash** (Cloudflare) | Needs a GPU | not runnable | — |
| TF-IDF + logistic regression, synthetic data | Laptop CPU | 17 *(see note)* | < 0.01 s |

*Note: the TF-IDF result is optimistic, because the 18 test narrations use merchants that also
appear in the synthetic training data. The real test is on the user's own labelled transactions.*

### What we learned along the way

1. **Laya is a "decision model" with no domain knowledge.** It reads the narration and the option
   names, but it doesn't know that Swiggy and Zomato are food delivery or that BigBasket sells
   groceries. It answered *Fixed / Recurring Deposit* for Swiggy with **98% confidence**. Its own
   model card warns that it is over-confident until calibrated.
2. **Prompt changes didn't fix it.** We tried a JSON state, a plain-text state, names with and
   without descriptions, and a two-step question. Accuracy stayed at 33–56%.
3. **A hidden token budget was cutting our options short.** Reading Laya's source showed that it
   fits the question and all options into **192 tokens**. With 23 options, each option gets about
   7 tokens, so our helpful category descriptions were truncated into noise. We now send
   **category names only**.
4. **Big decision models need big hardware.** We checked Clef on Hugging Face before trying to
   run it. Clef has 27 B parameters (55 GB of weights) and Clef-Flash has 9.4 B (19 GB). Both are
   tested on H200 GPUs. Estimated from Laya's measured speed, Clef-Flash would need about
   25–50 s per transaction on this CPU, if it fitted in memory at all.
   **Rule of thumb: memory ≈ parameters × bytes per parameter (BF16 = 2), plus about 20%.**
5. **Two integration surprises.**
   - The TypeSafe SDK compresses requests over 1 KB with zstd, which Laya doesn't accept. We fixed
     it with `compression=False`.
   - The first weight download from Hugging Face stalled silently. A restart resumed it. No
     Hugging Face key is needed.

## 3. The decision: fine-tune Laya on synthetic data

Laya's authors report that fine-tuning is where accuracy comes from: on their typed-decision
benchmark, fine-tuning raised the score from **0.362 to 0.766**. That gave us an approach that
satisfies all three constraints:

| Constraint | How it's met |
|---|---|
| Privacy | Training data is **100% synthetic**: brand names plus random references and names. The real transactions are used only locally, to measure accuracy. |
| No GPU | Training runs on a **free Kaggle GPU** (2×T4). The trained model runs on the laptop CPU. |
| Cost | Kaggle's free tier, open-source Laya (Apache-2.0), and an MIT-licensed seed dataset |

**The data.** We started from an MIT-licensed public generator of synthetic Indian narrations
(Sumeetgpt, 970 rows, 21 categories). We extended it to our 32 categories and to both directions
(money in and money out), and added the narration formats seen in Axis and SBI statements. The
result is 4,800 rows, 150 per category, split 90/10. **Laya's own `dry_run` accepted all rows,
with none skipped.**

**The safeguard.** The fine-tuned model is adopted only if it reaches **at least 85% on the user's
own hand-labelled transactions** and clearly beats base Laya. The TF-IDF baseline runs in the same
evaluation, so we also learn whether a 0.4 B-parameter model is worth it over a tiny classic one.

## 4. Results

*To be filled in after the first Kaggle run.*

| Model | 18 handwritten | ~100 real, hand-labelled | Time per transaction |
|---|---|---|---|
| Laya base (`laya-english`) | 7–10 / 18 | — | ~1–2 s |
| **Laya fine-tuned (`laya-finance`)** | — | — | — |
| TF-IDF baseline | 17 / 18 | — | < 0.01 s |
| Jev (cloud, reference) | 18 / 18 | — | 0.4 s |

## 5. Lessons

- **Measure on one fixed test set from day one.** Our 18 narrations made every option directly
  comparable and turned opinions into numbers.
- **"Open-source equivalent" doesn't mean "same quality".** Laya speaks Jev's API, but it is a
  0.4 B encoder. It knows the *form* of the task, not the *world* (merchants).
- **Read the source when results look wrong.** The 192-token option budget was undocumented in
  the places we looked, and it explained part of the poor accuracy.
- **Check hardware before downloading.** Parameter count and tensor type on the model page tell
  you within a minute whether a model can run on your machine.
- **Synthetic data solves privacy, not realism.** It teaches formats and common merchants. Real,
  locally kept corrections are the next step if synthetic rounds plateau.
- **Always keep a cheap baseline.** A classifier trained in one second is the bar any large model
  must clear.

## How to reproduce

The full step-by-step guide is in [`backend/training/README.md`](../backend/training/README.md).

## Sources

- Laya: [github.com/NandhaKishorM/laya](https://github.com/NandhaKishorM/laya) (Apache-2.0)
- Seed data: [Sumeetgpt/indian-transaction-categorization-synthetic](https://huggingface.co/datasets/Sumeetgpt/indian-transaction-categorization-synthetic) (MIT)
- Clef: [huggingface.co/Cloudflare/clef](https://huggingface.co/Cloudflare/clef) and [Cloudflare/clef-flash](https://huggingface.co/Cloudflare/clef-flash)
- Jev: [docs.typesafe.ai](https://docs.typesafe.ai)
