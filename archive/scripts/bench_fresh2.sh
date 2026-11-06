#!/bin/bash
# The one run on the fresh forms: locked settings in results/bench/LOCK_fresh2.json, one arm at a time. Finished forms are never repeated.
cd /home/tudao/project; P=$PWD
export HF_HOME=$P/.cache/hf PLAYWRIGHT_BROWSERS_PATH=$P/.cache/pw PYTHONWARNINGS=ignore CUDA_VISIBLE_DEVICES=""
C=models/ultron-forms-0.1/a/model.safetensors,models/ultron-forms-0.1/b/model.safetensors
for s in 1 2 3; do
  .venv/bin/python experiments/bench/run_bench.py plain fresh2_plain_s$s fresh $s > logs/bench/fresh2_plain_s$s.log 2>&1; echo plain $s exit $?
  .venv/bin/python experiments/bench/run_bench.py s1 fresh2_s1_s$s fresh $s $C 0.9 > logs/bench/fresh2_ultron_s$s.log 2>&1; echo ultron $s exit $?
  .venv/bin/python experiments/bench/run_bench.py s1 fresh2nm_s1_s$s fresh $s "" 0.9 > logs/bench/fresh2_nomodel_s$s.log 2>&1; echo no-model $s exit $?
done
