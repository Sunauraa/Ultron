"""Write a model's chat template with thinking turned off. Usage: nothink_template.py hf/name OUT"""

import glob
import json
import sys

name, out = sys.argv[1], sys.argv[2]
config = glob.glob(f".cache/hf/hub/models--{name.replace('/', '--')}/snapshots/*/tokenizer_config.json")[0]
template = json.load(open(config))["chat_template"]
assert "enable_thinking" in template
open(out, "w").write("{%- set enable_thinking = false %}\n" + template)
