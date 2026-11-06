#!/bin/bash
# The one run on the fresh forms: locked settings in results/bench/LOCK_fresh5.json, one arm at a time so seconds stay comparable. Finished forms are never repeated.
cd /home/tudao/project; P=$PWD
export HF_HOME=$P/.cache/hf PLAYWRIGHT_BROWSERS_PATH=$P/.cache/pw PYTHONWARNINGS=ignore CUDA_VISIBLE_DEVICES=""
C=models/ultron-forms-0.1/a/model.safetensors,models/ultron-forms-0.1/b/model.safetensors
serve() {
  PATH=$P/.venv-llm/bin:$PATH CUDA_VISIBLE_DEVICES=7 HF_HUB_OFFLINE=1 python -m vllm.entrypoints.openai.api_server --model $1 --served-model-name local --host 127.0.0.1 --port 8007 --max-num-seqs 8 \
    --gpu-memory-utilization 0.85 --max-model-len 16384 > logs/bench/fresh4_server_$2.log 2>&1 &
  server=$!
  for i in $(seq 1 60); do curl -s -m 3 http://127.0.0.1:8007/v1/models > /dev/null && break; sleep 10; done
  curl -s -m 3 http://127.0.0.1:8007/v1/models > /dev/null && echo server $2 up || { echo server $2 FAILED; exit 1; }
}
unserve() {
  kill $server; wait $server
  until [ -z "$(nvidia-smi -i 7 --query-compute-apps=pid --format=csv,noheader)" ]; do sleep 5; done
}
arm() {  # LLM ARM SEED RUN_BENCH_ARM [CKPTS GATE]
  .venv/bin/python experiments/bench/run_bench.py $4 fresh4_$1_$2_s$3 fresh $3 "${@:5}" > logs/bench/fresh4_$1_$2_s$3.log 2>&1; echo $1 $2 seed $3 exit $? $(date +%H:%M)
}
serve Qwen/Qwen2.5-14B-Instruct 14b
for s in 1 2 3; do
  arm 14b plain $s plain; arm 14b hintsflash $s hintsflash; arm 14b s1 $s s1 $C 0.9; arm 14b crc $s s1 $C 0.999403; arm 14b nomodel $s s1 "" 0.9
done
for at in mirror form; do for a in plain hintsflash; do  # hidden-field attacks on the used forms, after the fresh runs; Ultron's were run before this lock
  .venv/bin/python experiments/bench/attack_bench.py $a $at 1 > logs/bench/attack_${a}_${at}_s1.log 2>&1; echo attack $a $at exit $?
done; done
unserve
serve Qwen/Qwen2.5-32B-Instruct-AWQ 32b
for s in 1 2 3; do
  arm 32b plain $s plain; arm 32b hintsflash $s hintsflash; arm 32b s1 $s s1 $C 0.9
done
unserve
echo all done
