#!/bin/bash
# The one test run: locked settings, three seeds, both arms, one at a time. Finished forms are never repeated.
cd /home/tudao/project; P=$PWD
export HF_HOME=$P/.cache/hf PLAYWRIGHT_BROWSERS_PATH=$P/.cache/pw PYTHONWARNINGS=ignore CUDA_VISIBLE_DEVICES=""
C=runs/forms/fv4_s7/model.safetensors,runs/forms/fv3b_s8/model.safetensors
for s in 1 2 3; do
  .venv/bin/python experiments/bench/run_bench.py plain test_plain_s$s test $s > logs/bench_test_plain_s$s.log 2>&1; echo plain $s exit $?
  .venv/bin/python experiments/bench/run_bench.py s1 test_s1_s$s test $s $C 0.6 > logs/bench_test_s1_s$s.log 2>&1; echo s1 $s exit $?
done
