# LoRA training on the Razer

AutoManga trains character LoRAs on a separate GPU machine ("the trainer",
the Razer at 192.168.1.31) with [ai-toolkit](https://github.com/ostris/ai-toolkit).
The Mac keeps the datasets, pushes them over scp, launches the job over ssh,
polls its log and pulls the finished `.safetensors` into SwarmUI.
Code: `backend/training.py` (ssh/scp), `backend/api/training.py` (routes,
job), `backend/training_templates/sdxl_lora.yaml.tmpl` (the recipe),
`frontend/src/components/characters/TrainingPanel.tsx` (UI).

## One-time setup (Linux trainer; Fedora 45 on the Razer)

1. **SSH key**: the Mac's key in `~/.ssh/authorized_keys` on the trainer.
   `ssh -o BatchMode=yes pless84@192.168.1.31 true` must succeed without a prompt.
2. **ai-toolkit** in `~/ai-toolkit` with a CUDA venv (0.13.23; git ecee894 now):
   ```sh
   git clone https://github.com/ostris/ai-toolkit ~/ai-toolkit && cd ~/ai-toolkit
   python3.12 -m venv venv && venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cu130
   venv/bin/pip install -r requirements.txt
   venv/bin/python -c "import torch; print(torch.cuda.is_available())"   # True
   ```
   Jobs run `venv/bin/python run.py <config>`; the web UI (`run_linux.sh`) is not needed.
3. **Base model**: the checkpoint the comics are painted with, copied once:
   ```sh
   ssh pless84@192.168.1.31 mkdir -p models
   scp ~/SwarmUI/Models/Stable-Diffusion/Stylized/arthemyComics_v80.safetensors \
       pless84@192.168.1.31:models/
   shasum -a 256 ~/SwarmUI/Models/Stable-Diffusion/Stylized/arthemyComics_v80.safetensors
   ssh pless84@192.168.1.31 sha256sum models/arthemyComics_v80.safetensors   # same (c6ba4ee4…)
   ```
4. **Keep jobs alive**: jobs run under `setsid nohup`, so they survive the ssh
   connection and an AutoManga restart. They do not survive the trainer
   rebooting or sleeping: disable suspend while on AC (and keep it on AC).
   `loginctl show-user pless84 -p Linger` is `yes` on the Razer.

## Settings (`data/settings.json` → `training`)

| key | default | |
|---|---|---|
| `host` | `pless84@192.168.1.31` | ssh destination |
| `os` | `linux` | only Linux is implemented (Windows: not yet) |
| `toolkitDir` | `~/ai-toolkit` | `~` = the trainer's `$HOME` |
| `python` | `venv/bin/python` | relative to `toolkitDir` |
| `baseModel` | `/home/pless84/models/arthemyComics_v80.safetensors` | |
| `loraFolder` | `Comics` | under `~/SwarmUI/Models/Lora` on the Mac |
| `sampling` | `false` | ai-toolkit preview images; on 8 GB they OOM (see below) |

## Recipe

The sf_* LoRAs' config (`~/ai-toolkit/output/sf_mara/config.yaml`) verbatim:
LoRA linear/alpha 16, UNet only, fp16 saves every 500 (keep 3), captions from
`.txt` with 0.05 dropout, latents cached to disk, buckets 768/1024, batch 1,
1500 steps, gradient checkpointing, ddpm, adamw8bit, lr 1e-4, bf16, SDXL
`low_vram`. Per job: name, trigger, dataset folder, base model, steps,
sample prompts, and `disable_sampling` (from `sampling`).

## On the trainer

```
~/automanga-training/<name>/dataset/     img_NNN.png + .txt (pushed)
~/automanga-training/<name>/config.yaml  rendered config
~/automanga-training/<name>/train.log    stdout+stderr; train.log.exit = exit code
~/ai-toolkit/output/<name>/              checkpoints; <name>.safetensors = final
```

Remove both directories to retrain a name from scratch.

## Using it

Characters tab → a character → **Train LoRA**: create the dataset (name and
trigger word, e.g. `amnova`), add ≥ 15 images (upload, import the current
project's panels, or **Generate 24** from the appearance text), **Start
training**. 1500 steps take about 25 minutes on the RTX 3070 Laptop
(≈1.05 it/s; a 100-step run took 2 min 20 s including caching). When done the
LoRA is in SwarmUI as `Comics/<name>` and set on the character; copy the
`lora NAME: Comics/<name> 0.8 <trigger>` line into a `.comic` script.

## Troubleshooting

- **`CUDA out of memory` in `vae.decode` during `sample`**: the preview
  sampling at 832x1216 doesn't fit next to the model in 8 GB. Keep
  `sampling: false`.
- **Job failed "process is gone without an exit code"**: the trainer
  rebooted or the process was killed. On 2026-11-17 the Razer reset itself
  (no shutdown in the journal, "uncleanly shut down") while caching latents,
  minutes after an NVRM out-of-memory with Steam running; close games before
  training.
- **"has checkpoints on the trainer"**: `output/<name>` holds saves from an
  earlier run. Start with `resume` to continue it, pick another name, or
  delete the directory.
- **Poll errors** (`pollError` in the job) are shown and retried; the job
  keeps running on the trainer.
