## How to locally run LLMs

i've ran [Qwen3.7-4B-GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF) on my shitbox for scrapping OLX.ua

shitbox specs:
OC: win10 (22H2)
CPU: Intel core i7-3740QM 2.7 GHz
RAM: 16 GB DDR3
GPU: Inter(R) HD Graphics 4000 (32MB)

### What to check before ran

1. Check hardware
   my shitbox has i7-3740QM with Ivy Bridge (2012) that has AVX and F16C, but not AVX2 or FMA, which Intel introduced with Haswell in 2013. The HD Graphics 4000 contributes nothing: no CUDA, no usable Vulkan path — so inference is pure CPU.

2. Use wsl (for windows oc)
   check the bridge on your CPU:

```bash
grep -o -E 'avx2|avx|fma|f16c' /proc/cpuinfo | sort -u
```

for my case it's `avx` and `f16c`, if your shitbox uses more modern CPU it'd be `avx2` or `fma`.

Optionally, i set in `.wslconfig` for `[ws12]` section memory at `memory=12GB` (default is ~8GB)

### Build llama.cpp

```bash
sudo apt update && sudo apt install -y build-essential cmake git libcurl4-openssl-dev python3-venv
git clone https://github.com/ggml-org/llama.cpp && cd llama.cpp
cmake -B build -DGGML_NATIVE=OFF -DGGML_AVX2=OFF -DGGML_FMA=OFF
cmake --build build --config Release -j8 --target llama-server llama-cli
```

The three flags stop CMake from probing the (modern) build conventions and producing a binary that dies with "illegal instruction" on my chip, so you may not need them for your shitbox.

### Install Qwen3.5-4B

The official unsloth GGUF repo exists with all standard quants, and the documented launch pattern is:

```bash
./build/bin/llama-server -hf unsloth/Qwen3.5-4B-GGUF:Q4_K_M \
  -c 8192 -t 4 --port 8080 --reasoning off
```

First run downloads ~2.5–3 GB. Two flags deserve explanation:
[-] `--reasoning off`: disables Qwen3.5's default thinking mode, which would otherwise burn minutes of <think> tokens per article on this CPU
[-] `-t 4` uses physical cores only; test against `-t 8` since bandwidth-bound inference often doesn't benefit from hyperthreads.

Smoke-test by opening `http://localhost:8080` in your browser (llama-server ships a web UI) or with curl:

```bash
curl http://localhost:8080/v1/chat/completions -H "Content-Type: application/json" -d '{
  "messages": [{"role":"user","content":"Name one Linux command."}],
  "max_tokens": 64, "temperature": 0.7
}'
```

### Run LLM

The Python file I created does the full loop: pulls RSS feeds → extracts article text with trafilatura → asks the model for structured JSON (summary, 1–10 relevance score, tags) → drops anything below relevance 6 → sends the rest to your Telegram chat. URLs are logged in seen.json so nothing repeats, and it strips stray <think> tags as a safety net. Setup inside Ubuntu:

```bash
mkdir ~/llm-digest && cd ~/llm-digest   # save digest.py here
python3 -m venv .venv && source .venv/bin/activate
pip install feedparser httpx trafilatura openai
```

Then the Telegram side: message @BotFather in Telegram, run /newbot, and copy the token. Send your new bot any message, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser - your chat_id is in the JSON response. Put both into a small run.sh next to the script:

```bash
#!/usr/bin/env bash
export TELEGRAM_BOT_TOKEN="<YOUR_TOKEN>"
export TELEGRAM_CHAT_ID="<YOUR_CHAT_ID>"
cd ~/llm-digest
./.venv/bin/python digest.py >> digest.log 2>&1
```

Edit `FEEDS` and `INTERESTS` at the top of the script to match what you want to track, keep llama-server running in one terminal, and execute bash run.sh in another to test. The request timeout is set to 15 minutes because CPU inference on a 6000-character article genuinely can take that long when prompt processing is slow.

