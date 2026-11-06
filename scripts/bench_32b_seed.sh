#!/bin/bash
# One seed of the 32B fresh run on its own GPU and port, so seeds run in parallel. Usage: bench_32b_seed.sh SEED GPU PORT
# Settings as in results/bench/LOCK_fresh5.json; LOCK_fresh5b.json records the split. All arms of a seed share one GPU, one at a time.
cd /home/tudao/project; P=$PWD; s=$1; g=$2; port=$3
export HF_HOME=$P/.cache/hf PLAYWRIGHT_BROWSERS_PATH=$P/.cache/pw PYTHONWARNINGS=ignore CUDA_VISIBLE_DEVICES="" ULTRON_LLM_PORT=$port
C=models/ultron-forms-0.1/a/model.safetensors,models/ultron-forms-0.1/b/model.safetensors
PATH=$P/.venv-llm/bin:$PATH CUDA_VISIBLE_DEVICES=$g HF_HUB_OFFLINE=1 python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen2.5-32B-Instruct-AWQ --served-model-name local --host 127.0.0.1 --port $port --max-num-seqs 8 \
  --gpu-memory-utilization 0.85 --max-model-len 16384 > logs/bench/fresh4_server_32b_s$s.log 2>&1 &
server=$!
for i in $(seq 1 60); do curl -s -m 3 http://127.0.0.1:$port/v1/models > /dev/null && break; sleep 10; done
curl -s -m 3 http://127.0.0.1:$port/v1/models > /dev/null && echo server 32b seed $s up on GPU $g || { echo server FAILED; kill $server; exit 1; }
arm() {
  .venv/bin/python experiments/bench/run_bench.py $3 fresh4_32b_$1_s$s fresh $s "${@:4}" > logs/bench/fresh4_32b_$1_s$s.log 2>&1; echo 32b $1 seed $s exit $? $(date +%H:%M)
}
arm plain x plain; arm hintsflash x hintsflash; arm s1 x s1 $C 0.9
kill $server; wait $server
echo seed $s done
