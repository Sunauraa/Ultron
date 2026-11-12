#!/bin/bash
# Usage: train_forms.sh DATA RUN SEED [extra train.py args]
cd "$(dirname "$0")/.."
export CUBLAS_WORKSPACE_CONFIG=:4096:8 PYTHONPATH=$PWD/third_party/cua/libs/cua-s1/python/src HF_HOME=$PWD/.cache/hf CUDA_VISIBLE_DEVICES=7 PATH=$PWD/.venv-llm/bin:$PATH
data=$1 run=$2 seed=$3; shift 3
python third_party/cua/libs/cua-s1/training/train.py train $data/train.jsonl --validation $data/validation.jsonl --output runs/forms/$run \
  --encoder tinyx --width 128 --rank 128 --layers 2 --heads 4 --context-tokens 224 --option-tokens 96 --batch-size 128 --epochs 3 --seed $seed --device cuda "$@" > logs/training/train_$run.log 2>&1
