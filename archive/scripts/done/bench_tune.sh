#!/bin/bash
# Tune the redesigned plugin on the old test forms, now used up and so tuning data. Plain runs test_plain_s* are reused.
cd /home/tudao/project; P=$PWD
export HF_HOME=$P/.cache/hf PLAYWRIGHT_BROWSERS_PATH=$P/.cache/pw PYTHONWARNINGS=ignore CUDA_VISIBLE_DEVICES=""
C=models/ultron-forms-0.1/a/model.safetensors,models/ultron-forms-0.1/b/model.safetensors
for s in 1 2; do
  .venv/bin/python experiments/bench/run_bench.py s1 t2g6_s1_s$s test $s $C 0.6 > logs/bench_t2g6_s$s.log 2>&1; echo gate0.6 $s exit $?
  .venv/bin/python experiments/bench/run_bench.py s1 t2g9_s1_s$s test $s $C 0.9 > logs/bench_t2g9_s$s.log 2>&1; echo gate0.9 $s exit $?
  .venv/bin/python experiments/bench/run_bench.py s1 t2llm_s1_s$s test $s "" 0.9 > logs/bench_t2llm_s$s.log 2>&1; echo no-forms-model $s exit $?
done
