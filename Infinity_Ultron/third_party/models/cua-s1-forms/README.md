---
license: mit
tags:
  - jev
  - system-one
  - computer-use
  - form-filling
  - option-attention
base_model: []
pipeline_tag: other
---

# cua-s1-forms

A small, jev-like ("System One") one-pass option scorer for GUI form filling, trained to
work as the decision layer behind [cua-driver](https://github.com/trycua/cua/tree/main/libs/cua-driver).

Unlike an autoregressive LLM, this model does not generate text. Given a UI element and a
list of typed options (one option per document entity, plus `check` / `click` / `skip`), it
returns one probability per option in a single forward pass — the same input/output
contract as TypeSafe's [Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev).
Every actionable element on a form is scored independently and in parallel in one batch;
execution order (fills, then checkboxes, then the one submit click) is decided by
downstream code, not the model.

Full writeup, training code, synthetic data generator and live Cua Driver integration:
https://github.com/trycua/cua/tree/main/libs/cua-s1.

## Architecture

- Byte-level embedding + 2-layer Transformer encoder (width 128, 4 heads) over the context
  and, separately, over each option's text
- jevlike's `AttentionHead`: each option becomes a query against the context tokens,
  producing an attended context vector, then a shared dot product turns each
  (option, attended-context) pair into one logit; softmax over the live option count
- 706,048 trainable parameters, 2.8 MB checkpoint (`state_dict` + `config` + training
  history + best validation metrics)

## Input / output

Context (one per element, byte-truncated to 224 bytes):
```
TASK fill the form from the document, then submit
FORM Northwind Clinic - New Patient Registration
ELEMENT Edit "Phone number" value=""
```
Options (one per document entity, plus the three fixed actions, byte-truncated to 96 bytes
each): `fill Tel: (503) 555-0142`, `fill DOB: 03/14/1987`, ..., `check`, `click`, `skip`.

Output: one probability per option. The executor picks the argmax, looks up the entity by
index if the action is `fill`, and orders the resulting actions before sending them to
cua-driver (`set_value` / `click`).

## Training

- 10,000 synthetic episodes (`cua_s1/synth.py`): random form (2–16 fields from a 55-concept
  catalogue with form-label/document-label synonyms), random person, random document with
  distractor entities and forced look-alike confuser pairs (e.g. `email` vs `street`,
  `phone` vs `emergency contact phone`, `state` vs `university`), random window-title
  suffixes and 20% title dropout
- Splits are disjoint by exact form field signature — a test form's field set never appears
  in training
- AdamW, cosine schedule with warmup, 6 epochs, batch size 128, cross-entropy over the live
  option count

## Results (see the repo's `docs/RESULTS.md` for the full ladder)

| split | top-1 | notes |
| --- | ---: | --- |
| synthetic test (form-disjoint, ~15k decisions) | 99.95% | hard confuser pairs forced in |
| real demo eval (3 real forms + 3 real PDFs, 196 decisions, nothing synthetic) | 100% | |
| shuffled-context control | 37% | confirms the model reads the element, not option statistics |

Head-to-head against the real hosted Jev API (`jev-latest`, zero fine-tuning, same task):
99.7% for this model vs 83.6% for hosted Jev overall; 96% for hosted Jev on decisions that
require real judgment (fill vs check vs click) and 74% on recognizing an already-filled
field as a no-op — a convention this model was trained on and hosted Jev was not. Full
numbers in the repo.

## Files

- `cua-s1-forms.safetensors` + `cua-s1-forms.json` — the checkpoint in the format
  `cua_s1.checkpoint` expects: tensors only in safetensors, everything else (architecture
  config, a SHA-256 signature over the tensors, free-form metadata) in a plain JSON
  sidecar. This is the format to use; `cua_s1`'s own loader rejects pickled `.pt`/`.pth`
  files by design (arbitrary pickle is a code-execution risk for a public checkpoint).
- `cua-s1-forms.pt` — the original PyTorch pickle checkpoint, kept only for anyone still
  loading it directly with `torch.load(..., weights_only=False)` outside `cua_s1`. New code
  should use the safetensors pair above.

Both encode the exact same weights; converted with a script that reimplements
`cua_s1.checkpoint.save_checkpoint_files`'s exact document/signature format, and verified to
produce bit-for-bit identical model output against the original `.pt`.

## Usage

```python
from pathlib import Path
from huggingface_hub import hf_hub_download
from cua_s1.model import load_checkpoint, select_device

repo = "cua-ai/cua-s1-forms"
weights = Path(hf_hub_download(repo, "cua-s1-forms.safetensors"))
hf_hub_download(repo, "cua-s1-forms.json", local_dir=weights.parent)  # sits next to the weights

# validates format, version and SHA-256 tensor signature before returning
model, collator, config = load_checkpoint(weights, select_device("auto"))
```

See [`cua_s1/planner.py`](https://github.com/trycua/cua/tree/main/libs/cua-s1/python/src/cua_s1/planner.py)
for the full snapshot → score → order → execute loop against a live Cua Driver session.

## Limitations

- Only ever chooses among entities a PDF/document extractor already found as `Label: value`
  pairs; it cannot invent a value.
- Trained entirely on synthetic forms plus a small (196-decision) real eval; not validated
  on arbitrary real-world forms outside the demo set.
- Byte-level encoder, English-centric label vocabulary.
- Not calibrated with TypeSafe's RLCD method — this is an independent research checkpoint,
  not a reproduction of Jev.

## License

MIT.
