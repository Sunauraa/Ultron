#!/bin/bash
# The one run on the fresh forms: locked settings in results/bench/LOCK_fresh.json, one arm at a time. Finished forms are never repeated.
cd /home/tudao/project; P=$PWD
export HF_HOME=$P/.cache/hf PLAYWRIGHT_BROWSERS_PATH=$P/.cache/pw PYTHONWARNINGS=ignore CUDA_VISIBLE_DEVICES=""
C=models/ultron-forms-0.1/a/model.safetensors,models/ultron-forms-0.1/b/model.safetensors
mkdir -p logs/bench
for s in 1 2 3; do
  .venv/bin/python experiments/bench/run_bench.py plain fresh_plain_s$s fresh $s > logs/bench/fresh_plain_s$s.log 2>&1; echo plain $s exit $?
  .venv/bin/python experiments/bench/run_bench.py s1 fresh_s1_s$s fresh $s $C 0.9 > logs/bench/fresh_ultron_s$s.log 2>&1; echo ultron $s exit $?
  .venv/bin/python experiments/bench/run_bench.py s1 freshnm_s1_s$s fresh $s "" 0.9 > logs/bench/fresh_nomodel_s$s.log 2>&1; echo no-model $s exit $?
done
