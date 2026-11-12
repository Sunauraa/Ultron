# Ultron

**Ultra-Light Task Router for Online Navigation.** Ultron began as an optional plugin for the open-source Browser Use agent. It handles the routine parts of web forms and pop-ups with tiny on-device models and a few short, bounded LLM calls, and hands everything else to the full LLM agent. Its pop-up model now runs inside the job pipeline in [`../autoapply`](../autoapply), which is what this repository is about. This folder holds the research: the models, how they were built and tested, and the results.

- **Project 1, pop-ups:** a byte-level choice model of under 1M parameters picks the safe button on cookie banners and other pop-ups. It takes 47.5 ms on one CPU thread.
- **Project 2, forms:** a fast path fills a form from the user's document. It uses one short LLM call to match document lines to the remaining fields, a required-field check in code, and two short calls to submit and to finish.

## How it works

The plugin wraps the agent's next-action step. On each step:

1. **Pop-up:** if a dialog is open, the pop-up model picks a button. It acts only above a 0.6 confidence gate, otherwise the LLM agent decides.
2. **Form:** the forms model fills the text fields it is sure of, above a 0.9 gate.
3. **Settle:** one short LLM call picks a document line, or none, for each remaining field. The prompt shows the field labels and document lines, not the page.
4. **Required fields:** checked in code. If a required value is missing, the run stops and names the field instead of inventing a value.
5. **Submit:** one short call sees only the button labels, so planted page text can't steer it. One more short call confirms the page accepted the form.
6. **Hand-offs:** pages with password, file or card fields always go to the full agent, as does anything the fast path can't settle.
7. **Hidden fields:** text fields and buttons a person can't see are never filled or pressed. That means faded below half opacity through any parent, under 2 px, or off the page. Hidden copies of fields are how the EIA attack (Liao et al., ICLR 2025) steals what an agent types.

```python
from browser_use import Agent
from ultron import FastPath, install, parse_document

agent = Agent(task=task, llm=llm)
install(agent, FastPath(parse_document(document), forms_checkpoints, dialog_checkpoints, form_gate=0.9, finish=True))
await agent.run()
```

Submitting is opt-in through `finish=True`. Without it, Ultron fills fields and leaves submitting to the agent.

## Results

### Project 2: forms (final test)

- **Data:** 42 unseen real forms rebuilt from public pages and served locally, 22 in English and 20 in Vietnamese.
- **Runs:** 3 seeds, with Qwen2.5-14B and Qwen2.5-32B-AWQ as the agent's LLM.
- **Locking:** settings were locked before any result was read (`results/bench/LOCK_fresh5.json`).
- **The main metric, "handled correctly":** a form counts if it was sent with every scored field right and nothing extra filled, or if it was stopped while naming a required field the document can't fill.

| Average per seed | 14B default | 14B tuned | **14B + Ultron** | 32B default | 32B tuned | **32B + Ultron** |
|---|---:|---:|---:|---:|---:|---:|
| Handled correctly (of 42) | 19.3 | 15.7 | **31.0** | 17.0 | 24.0 | **35.0** |
| LLM calls | 429 | 391 | 132 | 222 | 306 | 120 |
| Prompt tokens | 3.05M | 0.96M | 0.17M | 1.50M | 0.75M | 0.09M |
| Wrong fields on sent forms | 21.0 | 28.3 | 3.0 | 21.3 | 13.7 | 1.0 |
| Extra fields filled | 5.3 | 20.3 | 16.7 | 6.7 | 12.3 | 13.0 |
| Choice controls answered (not scored) | 14.0 | 10.3 | 0 | 12.3 | 15.0 | 1.0 |

- **Columns:** "Default" is Browser Use with the benchmark's task. "Tuned" adds hints and flash mode, tuned for the LLM-only agent on the same used forms Ultron was designed on.
- **14B gain:** +11.7 forms handled correctly over default, 95% interval [+6.0, +17.3].
- **32B gain:** +11.0 over tuned [+6.7, +15.7], with 61% fewer LLM calls and 89% fewer prompt tokens.
- **Excluding unclear forms:** on the 36 forms where every required field has a clear answer, the gains are +10.0 and +9.3.
- **Ablations, 14B:**
  - **Without the tiny forms model:** 33.0 handled correctly [−5.0, 0.0 against Ultron]. That costs 21% more calls overall, but only 1% on the clear forms. So the gain comes from the routing design, not the forms model.
  - **With a conformal-risk-control gate** (Angelopoulos et al., ICLR 2024) instead of 0.9: 32.0 [0.0, +3.0]. Neither change was adopted after seeing these results.
- **Timing:** the 32B seeds ran in parallel on separate GPUs, so compare seconds within a column only. Full table: `results/bench/fresh4_table.txt`.

### Hidden-field attacks

These ran on 23 used forms with 14B and one seed. Each cell counts forms where typed data reached the attacker:

| Attack | LLM only, default | LLM only, tuned | Ultron, no defence | Ultron |
|---|---:|---:|---:|---:|
| Faded copy beside the real field | 0 | 2 | 8 | 0 |
| Separate hidden form | 17 | 16 | 7 | 1 |

The one remaining leak came from the agent's own LLM, after Ultron had handed the page over.

### Project 1: pop-ups (final test)

On 281 held-out pop-ups, at the locked gate of 0.6:

| | Answered | Right | Bad clicks | Right when it answers |
|---|---:|---:|---:|---:|
| Ultron pop-up model | 252 | 238 | 14 | 94.4% [90.9, 96.7] |
| Best LLM, Qwen2.5-32B, one call | 277 | 253 | 24 | 91.3% [87.4, 94.1] |
| Qwen2.5-14B agent, told the policy | 281 | 235 | 46 | 83.6% [78.9, 87.5] |
| Safe-button rules | 101 | 100 | 1 | 99.0% |

The model is about as accurate as the best LLM when it answers, at a tiny fraction of the compute. It declines more often (29 against 4), and declining isn't free. All 12 LLM setups are in `results/popups_llm/more/baselines_fair.txt`.

## Limitations

- **Labels:** the test sets were labelled with LLM help, not by independent people, and the same author built the system.
- **Simulated sites:** forms are rebuilt locally, nothing was submitted on a live site, and forms that need JavaScript are untested.
- **Pop-up markup:** test pop-ups use `role="dialog"`, which is exactly what the detector looks for.
- **Cost:** token counts aren't dollars, and prompt caching would narrow the gap.
- **Baselines:** no frontier API model was tested as the baseline.
- **What Ultron can't do:** answer choice controls or join document lines, such as first and last name into one field.
- **Remaining attacks:** a visible field labelled with an instruction is still open.

## Project layout

| Folder | What's in it |
|---|---|
| `ultron/` | The Browser Use plugin: `FastPath`, `install` and `parse_document` |
| `models/` | The shipped models: `ultron-dialogs-0.1` for pop-ups and `ultron-forms-0.1` for forms, two ensemble members each |
| `experiments/popups/` | Pop-up data capture, labelling, training-set building, scoring and baselines |
| `experiments/forms/` | Forms training data and real-form collection |
| `experiments/bench/` | The agent benchmark, attack benchmark, results tables and the conformal gate |
| `experiments/calibration.py` | Calibration of both models |
| `tests/` | Safety tests with a scripted LLM, plus the submit and finish check with a real LLM |
| `scripts/` | The locked final runs and the forms training wrapper |
| `docs/` | The demo page (published with GitHub Pages), the in-browser pop-up model (`weights.json`), the side-by-side video and its recorder |
| `data/` | Test sets (tracked) and generated training data (ignored, about 8 GB) |
| `results/` | Final results only: `bench/` for forms, `final_result.txt` and `popups_llm/` for pop-ups, `calibration/` |
| `archive/` | Superseded tuning runs, earlier locked attempts, old scripts and file backups, kept for audit |
| `third_party/` | The byte-level choice-model library and its training script |

`logs/`, `runs/`, `external/`, `tmp/`, `.cache/` and the two virtual environments are in `.gitignore`.

## Reproduce

All commands run from this folder (`ultron/`). GPU jobs set `CUDA_VISIBLE_DEVICES`. The plugin and benchmark run on CPU; only the LLM server and training need a GPU.

### 1. Environments

```bash
export P=$PWD HF_HOME=$PWD/.cache/hf PLAYWRIGHT_BROWSERS_PATH=$PWD/.cache/pw
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
python3.13 -m venv .venv-llm && .venv-llm/bin/pip install -r requirements-llm.txt
.venv/bin/playwright install chromium
```

- `.venv` runs the agent, the plugin and the benchmark on CPU, with Browser Use 0.13.14.
- `.venv-llm` runs the LLM server (vLLM 0.11) and training.
- The scripts expect Chromium at `.cache/pw/chromium-1248/`.

### 2. Train the models (optional: trained weights are in `models/`)

```bash
# Forms models: a = forms_v4 seed 7, b = forms_v3 seed 8, both 10 epochs
scripts/train_forms.sh data/forms/forms_v4 fv4_s7 7 --epochs 10
scripts/train_forms.sh data/forms/forms_v3 fv3b_s8 8 --epochs 10

# Pop-up models: data/popups/f2_15, seeds 7 and 8, 2 epochs
for s in 7 8; do
  CUDA_VISIBLE_DEVICES=0 PYTHONPATH=third_party/cua/libs/cua-s1/python/src .venv-llm/bin/python third_party/cua/libs/cua-s1/training/train.py train \
    data/popups/f2_15/train.jsonl --validation data/popups/f2_15/validation.jsonl --output runs/popups/g_w96_e2_s$s \
    --encoder tinyx --width 96 --rank 96 --layers 2 --heads 4 --context-tokens 480 --option-tokens 96 --batch-size 128 --epochs 2 --seed $s --device cuda
done
```

- **Model settings:** taken from each shipped model's `config.json`.
- **Pop-up training set:** confirmed as `f2_15`, because it reproduces the recorded validation NLL exactly (0.6256).
- **Forms training data:** built with `experiments/forms/synth_forms.py OUT EPISODES SEED` and `synth_extended.py`.
- **Pop-up data pipeline:** `capture_popups.py`, then `extract_items.py`, `label_buttons_llm.py` and `build_real2.py`.
- **Not recorded:** the exact arguments that built the training sets, for either model. The built sets are the record.

### 3. Safety tests

```bash
.venv/bin/python tests/test_ultron_safety.py      # 28 checks in a real browser with a scripted LLM, CPU only
.venv/bin/python tests/check_finish_llm.py        # submit and finish decisions with the real LLM (needs the server below)
```

### 4. LLM server

```bash
PATH=$P/.venv-llm/bin:$PATH CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-14B-Instruct --served-model-name local --host 127.0.0.1 --port 8007 \
  --max-num-seqs 8 --gpu-memory-utilization 0.85 --max-model-len 16384
```

- **32B:** use `--model Qwen/Qwen2.5-32B-Instruct-AWQ`.
- **Other ports:** the benchmark reads the port from `ULTRON_LLM_PORT`, default 8007.

### 5. Forms benchmark (Project 2)

```bash
C=models/ultron-forms-0.1/a/model.safetensors,models/ultron-forms-0.1/b/model.safetensors
# One arm: run_bench.py ARM NAME SPLIT SEED [FORMS_CHECKPOINTS [GATE]]
.venv/bin/python experiments/bench/run_bench.py plain      fresh4_14b_plain_s1      fresh 1
.venv/bin/python experiments/bench/run_bench.py hintsflash fresh4_14b_hintsflash_s1 fresh 1
.venv/bin/python experiments/bench/run_bench.py s1         fresh4_14b_s1_s1         fresh 1 $C 0.9
.venv/bin/python experiments/bench/run_bench.py s1         fresh4_14b_crc_s1        fresh 1 $C 0.999403   # conformal gate
.venv/bin/python experiments/bench/run_bench.py s1         fresh4_14b_nomodel_s1    fresh 1 "" 0.9        # no forms model
```

- **Full locked runs:** `scripts/bench_fresh4.sh` runs all 14B arms on 3 seeds. `scripts/bench_32b_seed.sh SEED GPU PORT` runs one 32B seed on its own GPU and server.
- **Table with 95% intervals:** `.venv/bin/python experiments/bench/bench_table.py fresh4 1 2 3`. The result is saved in `results/bench/fresh4_table.txt`.
- **Lock files:** settings and file hashes are in `results/bench/LOCK_fresh5.json` and `LOCK_fresh5b.json`.
- **Resuming:** a finished form is never run again, so a rerun into the same folder only fills gaps. Use a new name for a clean run.

### 6. Hidden-field attacks

```bash
.venv/bin/python experiments/bench/attack_bench.py ARM mirror|form 1   # ARM: plain, hintsflash, ultron or ultron_nofix
```

The Ultron arms ran at the conformal gate (0.999403), not the default 0.9.

### 7. Pop-ups (Project 1)

```bash
.venv/bin/python experiments/popups/score_dialogs.py models/ultron-dialogs-0.1/a dev     # tuning splits: dev, test, hard, susbench
.venv/bin/python experiments/popups/baselines_fair.py                                  # the final table on equal terms
```

`score_final.py` refuses to run while `results/final_result.txt` exists, so the locked final test can't be rerun into a better number.

### 8. Calibration and the conformal gate

```bash
.venv/bin/python experiments/calibration.py            # ECE, temperature scaling, normalised confidence for both models
.venv/bin/python experiments/bench/calibrate_gate.py 0.05
```

### 9. Video and demo page

```bash
ULTRON_LLM_PORT=8011 .venv/bin/python docs/record_side_by_side.py fresh fresh1_0     # needs a 32B server on that port
.venv/bin/python experiments/popups/export_demo.py docs models/ultron-dialogs-0.1/a models/ultron-dialogs-0.1/b
```

- **Video:** compares the tuned LLM-only agent with Ultron on one form, chosen by a rule fixed before recording: the English test form both arms handled correctly on all 3 seeds, with the tuned agent's call count closest to its median. Both get it right, in 22 s and 4 calls against 14 s and 3.
- **Pop-up model export:** `export_demo.py` writes `docs/weights.json` for the in-browser model on `docs/index.html`.
