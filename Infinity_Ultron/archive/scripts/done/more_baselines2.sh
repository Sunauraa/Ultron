#!/bin/bash
# Extra LLM baselines on the locked pop-up test. Each worker holds one model on disk, so two workers store at most two.
# Usage: more_baselines.sh GPU PORT short=hf/name[:flags] ...
# For each model: download, serve, sanity check on used pop-ups, one call per pop-up, Browser Use agent, delete the model.
cd /home/tudao/project
export HF_HOME=$PWD/.cache/hf PATH=$PWD/.venv-llm/bin:$PATH CUDA_VISIBLE_DEVICES=$1 LLM_PORT=$2 PLAYWRIGHT_BROWSERS_PATH=$PWD/.cache/pw
gpu=$1 port=$2; shift 2
out=$PWD/results/popups_llm/more; mkdir -p $out
for spec in "$@"; do
  short=${spec%%=*}; rest=${spec#*=}; model=${rest%%:*}; flags=""; [ "$rest" != "$model" ] && flags=${rest#*:}
  extra=(); nothink=0; export LLM_MAX_TOKENS=60
  case $flags in
    nothink) nothink=1 ;;
    harmony) extra=(--reasoning-parser openai_gptoss --tool-call-parser openai); export LLM_MAX_TOKENS=800 ;;
  esac
  huggingface-cli download "$model" --exclude "*.bin" "original/*" "metal/*" > logs/dl_$short.log 2>&1 || { echo "$short DOWNLOAD FAILED"; continue; }
  if [ $nothink = 1 ]; then  # vLLM 0.11 has no flag for this, so the model's own template gets thinking turned off
    python3 -I scripts/nothink_template.py "$model" logs/template_$short.jinja && extra=(--chat-template logs/template_$short.jinja)
  fi
  python -m vllm.entrypoints.openai.api_server --model $model --served-model-name local --host 127.0.0.1 --port $port --max-num-seqs 8 \
    --gpu-memory-utilization 0.85 --max-model-len 16384 "${extra[@]}" > logs/llm_$short.log 2>&1 &
  server=$!
  for i in $(seq 1 120); do
    python3 -c "import urllib.request as u;u.urlopen('http://127.0.0.1:$port/v1/models',timeout=3)" 2>/dev/null && break
    kill -0 $server 2>/dev/null || break
    python3 -c "import time;time.sleep(15)"
  done
  if kill -0 $server 2>/dev/null; then
    echo "$short up on gpu $gpu $(date +%H:%M)"
    (cd feasibility && ../.venv/bin/python preflight_llm.py) > logs/pre_$short.log 2>&1
    usable=$(sed -n 's/^usable answers \([0-9]*\) of 15$/\1/p' logs/pre_$short.log)
    echo "$short sanity check: ${usable:-0}/15 usable"
    if [ "${usable:-0}" -ge 12 ]; then
      if [ ! -e $out/${short}_policy_final.jsonl ]; then
        (cd feasibility && ../.venv/bin/python baseline_llm.py final $out/${short}_policy_final.tmp) && mv $out/${short}_policy_final.tmp $out/${short}_policy_final.jsonl
      fi
      echo "$short one-call finished $(date +%H:%M)"
      (cd feasibility && PYTHONWARNINGS=ignore ../.venv/bin/python llm_popups.py $out/${short}_agent_final.jsonl final) > logs/agent_$short.log 2>&1
      echo "$short agent finished $(date +%H:%M)"
    else
      echo "$short SKIPPED: failed the sanity check, final test not touched"
    fi
    kill $server; wait $server 2>/dev/null
  else
    echo "$short FAILED to start, see logs/llm_$short.log"
  fi
  rm -rf ".cache/hf/hub/models--${model//\//--}"
  echo "$short removed from disk: $(ls .cache/hf/hub | grep -c '^models--') stored"
done
