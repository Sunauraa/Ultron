#!/bin/bash
# Dev comparison after the blank-label and empty-field fixes. Both arms, one after the other.
cd /home/tudao/project; P=$PWD
export HF_HOME=$P/.cache/hf PLAYWRIGHT_BROWSERS_PATH=$P/.cache/pw PYTHONWARNINGS=ignore CUDA_VISIBLE_DEVICES=""
.venv/bin/python experiments/bench/run_bench.py plain dev2_plain_s1 dev 1 > logs/bench_dev2_plain_s1.log 2>&1; echo plain exit $?
.venv/bin/python experiments/bench/run_bench.py s1 dev2_s1_s1 dev 1 runs/forms/fv4_s7/model.safetensors,runs/forms/fv3b_s8/model.safetensors 0.6 > logs/bench_dev2_s1_s1.log 2>&1; echo s1 exit $?
