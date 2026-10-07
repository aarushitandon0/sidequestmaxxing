# Model export: Tinker checkpoint → GGUF on sqm-llm (P17, gate G3)

Script: `training/export_model.py` (one step per call). Steps that download, compute for a long
time, or upload only print their plan unless you add `--go`. Nothing here was run from the build
container (Tinker and huggingface.co are blocked there), so **the real pipeline is untested
end to end**. The script's logic is covered by `training/tests/test_export_model.py`, which uses fakes.

## 0. Prerequisites (your machine)
- A finished SFT run: `training/runs/<run>/summary.json` from `train_sft.py --go` (P15). The
  export uses its `best.sampler_path` (or pass `--sampler-path tinker://…`).
- The API venv plus `pip install -r training/requirements.txt`. That gives you `tinker-cookbook`, which pulls
  torch, transformers and huggingface_hub. Set `TINKER_API_KEY` in the environment.
- Disk: about 9 GB for the bf16 merge, 9 GB for the bf16 GGUF and about 3 GB for Q4_K_M (Qwen3.5-4B).
  RAM: the merge loads the model in bf16, so plan on about 16 GB.
- llama.cpp, built from a recent `master`. Its `convert_hf_to_gguf.py` registers
  `Qwen3_5ForConditionalGeneration` / `Qwen3_5ForCausalLM` (checked 2026-10-07):
  ```
  git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp
  cd ~/llama.cpp && pip install -r requirements/requirements-convert_hf_to_gguf.txt
  cmake -B build && cmake --build build --config Release -t llama-quantize llama-server
  ```
  Use the same llama.cpp version as the `ghcr.io/ggml-org/llama.cpp:server` image you serve
  with (or newer). An older server may not load a GGUF written by a newer converter.
- Set `hf_repo` in `training/configs/export.json` to a repo you own (it will be **public**).
  Check that the licence is still Apache-2.0 on https://huggingface.co/Qwen/Qwen3.5-4B.

## 1. Steps
Run from the repo root. Leave off `--go` first to see the plan.
```
RUN=<run folder name>
python training/export_model.py download --run $RUN --go     # Tinker weights -> adapter/
python training/export_model.py merge    --run $RUN --go     # cookbook build_hf_model -> merged/ (bf16 safetensors)
python training/export_model.py gguf     --run $RUN --llama-cpp ~/llama.cpp --go   # bf16 GGUF -> Q4_K_M
python training/export_model.py sha      --run $RUN          # prints MODEL_URL and MODEL_SHA256
python training/export_model.py card     --run $RUN          # writes README.md (model card, with the SHA)
less training/data/export/$RUN/README.md                     # review the card
HF_TOKEN=… python training/export_model.py publish --run $RUN --go   # PUBLIC upload: card + GGUF
```
- Work files go to `training/data/export/<run>/` (gitignored). Metadata (sampler path, SHA,
  size, URL) goes to `training/runs/<run>/export.json`. Commit that file.
- Why not PEFT `merge_and_unload`: see DECISIONS D-60.
- Optional local check before uploading: `~/llama.cpp/build/bin/llama-server -m training/data/export/$RUN/<file>.gguf --port 8080`, then
  `python scripts/bench_llm.py --base-url http://localhost:8080 --n 20`.
- `publish` refuses if the GGUF changed after `sha`. Never paste `HF_TOKEN` into chat. Use a
  write token and revoke it after publishing.

## 2. Redeploy sqm-llm
1. Render dashboard → `sqm-llm` → Environment:
   - `MODEL_URL` = the printed `https://huggingface.co/<repo>/resolve/main/<file>.gguf`
   - `MODEL_SHA256` = the printed hash
   - `MODEL_FILE` = the GGUF file name (e.g. `sidequestmaxxing-quest-master-Q4_K_M.gguf`). A **new**
     name makes the entrypoint download the new model instead of reusing the old `quest.gguf` on
     the disk. The old file stays on the disk; delete it from the Render shell if space is short
     (10 GB disk).
2. Save, then **Manual Deploy → Deploy latest commit**. The entrypoint downloads the file, checks it
   against `MODEL_SHA256` *before* moving it into place, checks it again on every boot,
   then starts `llama-server`. A mismatch deletes the file and exits, so the deploy fails
   loudly instead of serving the wrong model.
3. Check the logs: the download, `…: OK` from `sha256sum`, then the server listening. Then run
   `API_BASE_URL=https://<sqm-api>.onrender.com bash scripts/smoke_test.sh`.
4. If the Q4_K_M plus KV cache doesn't fit the plan's RAM, the service will OOM. Changing the plan
   costs money: check the price and ask before you change `plan:` in `render.yaml`.

## 3. Re-run the eval against the SERVED model
`sqm-llm` is a private service, so run the eval from somewhere that can reach it:
- **Simplest:** run the same GGUF locally with the same llama.cpp image (identical file, same
  SHA):
  ```
  docker run --rm -p 8080:10000 -e MODEL_URL=<url> -e MODEL_SHA256=<sha> -e MODEL_FILE=<file> \
    -v sqm-models:/data $(docker build -q services/llm)
  ```
- **Or on Render:** open a Shell on `sqm-api` (it can reach `sqm-llm`'s `hostport`) and run the
  eval from there. You'd need to install the training deps in that shell.

Then (the label must match the model id the server reports; the run refuses otherwise):
```
curl -s http://localhost:8080/v1/models          # read the id (the GGUF path or file name)
python training/eval.py run --arm tuned    --base-url http://localhost:8080 --label <id>
# swap MODEL_URL/MODEL_SHA256/MODEL_FILE to the base model's Q4_K_M GGUF (same quantization), restart, then:
python training/eval.py run --arm baseline --base-url http://localhost:8080 --label <base id>
python training/eval.py report --judge-url <url> --judge-model <id> --judge-family <family>  # judge: see D-59; writes evals/results.{json,md}
```
Commit `evals/` as written by the scripts. Never edit the numbers by hand. Record the served GGUF's
SHA-256 next to the results in `docs/DECISIONS.md`, so the claim maps to the exact file that ships.
