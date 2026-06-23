"""Kaggle runner: one Ohmatic leg on the third-party `pcbschemagen` suite (PCBBench-62).

Parametric over the three shipped Ohmatic variants via env:

    OHMATIC_BENCH_MODEL = q4 | q8 | bf16   (default q4)
    OHMATIC_BENCH_REF   = git ref to check out                     (default main)
    OHMATIC_BENCH_N     = cap the suite to the first N stratified tasks (default 0 = all 62)

This runs the SHIPPED PUBLIC pipeline (public T5 normalizer -> Qwen -> ERC -> retries ->
killswitch) via the standard cross_model harness - no private loop-normalizer code, so the
leg is reproducible from public artifacts alone. Scoring is OUR ERC on THEIR prompts (a
third-party external-validity probe); see make_pcbschemagen_suite.py for provenance/licensing.

HF_TOKEN: env first (inject at launch into a launch-only copy - never commit it), then a
Kaggle Secret named HF_TOKEN. The merged repo + GGUFs are private, so a token is required.

VRAM: q4 (~4.7 GB) and q8 (~8.5 GB) fit one T4. bf16 (~16 GB) does
NOT fit a single 15 GB T4 - run it on 2xT4 (the hf backend shards) or an A100.

Output: results/ and verified/ are copied to /kaggle/working under DISTINCT names
(<model>.results.jsonl / <model>.verified.jsonl) so the raw generations survive next to the
verified outcomes (the earlier kernel copied both to the same name and lost the raw rows).
"""
import glob
import os
import shutil
import subprocess
import sys
import time

T0 = time.time()
def log(*a): print(f"[{time.time() - T0:7.1f}s]", *a, flush=True)

MODEL = os.environ.get("OHMATIC_BENCH_MODEL", "q4")
REF   = os.environ.get("OHMATIC_BENCH_REF", "main")
NCAP  = os.environ.get("OHMATIC_BENCH_N", "0")
IS_GGUF = MODEL in ("q4", "q8")
log(f"leg: model={MODEL} ref={REF} n={NCAP or 'all'} backend={'llamacpp' if IS_GGUF else 'hf'}")
subprocess.run(["nvidia-smi", "-L"], check=False)

# --- HF token (env -> Kaggle Secret), token-free file ---
HF_TOKEN = os.environ.get("HF_TOKEN")
if not HF_TOKEN:
    try:
        from kaggle_secrets import UserSecretsClient
        HF_TOKEN = UserSecretsClient().get_secret("HF_TOKEN")
    except Exception:
        HF_TOKEN = None
if HF_TOKEN:
    os.environ["HF_TOKEN"] = HF_TOKEN
    os.environ["HUGGING_FACE_HUB_TOKEN"] = HF_TOKEN
print("HF token present:", bool(HF_TOKEN), flush=True)

def pip(*a): subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *a])

log("deps")
# bf16 hf backend loads Qwen via transformers (needs Qwen3 arch, >=4.51); the GGUF legs keep
# the known-good 4.47.0 (T5-clean + native DBS) that q4/q8 run on.
pip("transformers==4.47.0" if IS_GGUF else "transformers==4.51.3",
    "sentencepiece", "accelerate", "datasets", "huggingface_hub")
if IS_GGUF:
    log("llama-cpp-python (CUDA)")
    try:
        pip("llama-cpp-python", "--prefer-binary", "--extra-index-url",
            "https://abetlen.github.io/llama-cpp-python/whl/cu124")
    except Exception as e:
        log("prebuilt wheel failed -> source CUDA build", e)
        os.environ["CMAKE_ARGS"] = "-DGGML_CUDA=on"
        pip("llama-cpp-python")

# --- get the repo, then deliver the benchmark code ---
# Base repo (inference/verifier/shared pipeline) from GitHub main. The bench code (this
# branch's eval/benchmark/cross_model/*) is delivered one of two ways:
#   * OHMATIC_BENCH_REF != main  -> check out a PUSHED branch, or
#   * OHMATIC_BENCH_CODE=<dir>   -> overlay a mounted Kaggle dataset of the bench files,
#                                  so an UNPUSHED branch can run without publishing it.
REPO = "/kaggle/working/Ohmatic"
subprocess.check_call(["git", "clone", "https://github.com/VittoriaLanzo/Ohmatic", REPO])
if REF and REF != "main":
    subprocess.check_call(["git", "-C", REPO, "checkout", REF])
CODE = os.environ.get("OHMATIC_BENCH_CODE")          # e.g. /kaggle/input/ohmatic-bench-code
if CODE and os.path.isdir(CODE):
    dst = f"{REPO}/eval/benchmark/cross_model"
    overlaid = []
    for f in sorted(os.listdir(CODE)):
        src = os.path.join(CODE, f)
        if os.path.isfile(src) and f.endswith(".py"):
            shutil.copy(src, os.path.join(dst, f)); overlaid.append(f)
    log(f"overlaid bench code from {CODE}: {overlaid}")

env = dict(os.environ)
env["PYTHONPATH"] = REPO
env["TOKENIZERS_PARALLELISM"] = "false"

def run(*a):
    log("RUN", " ".join(a))
    return subprocess.run([sys.executable, "-m", *a], cwd=REPO, env=env, check=False)

# --- build the suite from source (reproducible) ---
run("eval.benchmark.cross_model.make_pcbschemagen_suite")

# --- force regeneration for this model+suite, then generate -> verify -> report ---
for d in ("results", "verified"):
    p = f"{REPO}/eval/benchmark/cross_model/{d}/{MODEL}.jsonl"
    if os.path.exists(p):
        os.remove(p)

gen = ["eval.benchmark.cross_model.generate", "--model", MODEL, "--suite", "pcbschemagen"]
if NCAP and NCAP != "0":
    gen += ["--n", NCAP]
log("generate (shipped pipeline, pcbschemagen)…")
run(*gen)
log("verify (ERC)…")
run("eval.benchmark.cross_model.verify")
log("report…")
r = subprocess.run([sys.executable, "-m", "eval.benchmark.cross_model.report",
                    "--suite", "pcbschemagen", "--by-category"],
                   cwd=REPO, env=env, capture_output=True, text=True)
print(f"===== REPORT ({MODEL}, pcbschemagen / PCBBench) =====\n"
      + (r.stdout or "") + "\n" + (r.stderr[-800:] if r.stderr else ""), flush=True)

# --- preserve raw results AND verified outcomes under distinct names ---
for stage in ("results", "verified"):
    src = f"{REPO}/eval/benchmark/cross_model/{stage}/{MODEL}.jsonl"
    if os.path.exists(src):
        shutil.copy(src, f"/kaggle/working/{MODEL}.{stage}.jsonl")
print("PCBSG_LEG_COMPLETE", flush=True)
