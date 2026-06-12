# Converting Ohmatic-Qwen3-8B for in-browser WebGPU (WebLLM/MLC)

One-time job, ~30 GB disk, GPU not required for weight conversion.
Produces `Ohmatic-Qwen3-8B-q4f16_1-MLC`, the artifact the frontend's
"In-browser" engine loads (set at launch; until then the engine uses the
prebuilt base `Qwen3-8B-q4f16_1-MLC` for plumbing tests).

```bash
pip install --pre mlc-llm-nightly-cpu mlc-ai-nightly-cpu  # or the CUDA wheels

# 1. quantize + convert weights (input: the merged bf16 HF repo)
mlc_llm convert_weight VittoriaLanzo/Ohmatic-Qwen3-8B \
  --quantization q4f16_1 -o dist/Ohmatic-Qwen3-8B-q4f16_1-MLC

# 2. chat config (template: qwen3; context fits our 6k prompt + circuit)
mlc_llm gen_config VittoriaLanzo/Ohmatic-Qwen3-8B \
  --quantization q4f16_1 --conv-template qwen3 \
  --context-window-size 16384 \
  -o dist/Ohmatic-Qwen3-8B-q4f16_1-MLC

# 3. upload (public at launch; browsers can't carry private tokens safely)
huggingface-cli upload VittoriaLanzo/Ohmatic-Qwen3-8B-q4f16_1-MLC \
  dist/Ohmatic-Qwen3-8B-q4f16_1-MLC .
```

Wire-in: the browser engine reads `localStorage["ohmatic.webllmModel"]`;
register the custom model in WebLLM appConfig with `model` = the HF URL and
`model_lib` = the prebuilt Qwen3-8B q4f16_1 wasm from
github.com/mlc-ai/binary-mlc-llm-libs (same architecture as the base, no
custom compile needed). Requirements on the user side: WebGPU (the header
badge already checks activation) + ~6 GB GPU memory; weights cache in
IndexedDB after first load.

License note: the MLC repo must carry the same FSL-1.1 LICENSE as the parent.
