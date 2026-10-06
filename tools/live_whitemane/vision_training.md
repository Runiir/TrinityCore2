The vision checkpoint can learn the original archaeology, travel and guidance
contracts through frozen-encoder decision-head supervised learning. This pilot
also covers explicit Survey, pickup, depth and landing action facts. Its inputs
retain the full structured state under `controller`, matching the service's
text framing. Every example is synthetic and contains no image.

The checkpoint and SDK are pinned by `vision_task_head_sft_v1.json`. The trainer
requires CPU and at most two Torch threads, checks every tokenization for cuts,
caps the FP16 frozen-output cache at 256 MiB, balances tasks/actions, selects the
head using validation NLL, and calibrates scalar temperatures on validation only.
Test labels never select the model. Reversed option order is a separate test.

```bash
pixi run python -m tools.live_whitemane.vision_dataset \
  --config experiments/configs/client_harness/vision_task_head_sft_v1.json \
  --output /tmp/vision-task-sft-20261006/dataset.json
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=2 pixi run \
  --manifest-path tools/live_whitemane/vision/pixi.toml python \
  -m tools.live_whitemane.vision_train \
  --config experiments/configs/client_harness/vision_task_head_sft_v1.json \
  --dataset /tmp/vision-task-sft-20261006/dataset.json \
  --output /tmp/vision-task-sft-20261006/model
pixi run python -m tools.live_whitemane.vision_checkpoint \
  --experiment /tmp/vision-task-sft-20261006
```

Use a new experiment directory and checkpoint label for reruns; closed archives
are immutable. Checkpointing writes DVCLive metrics, pushes the exact DVC pointer,
verifies the remote object, then removes only that generated local experiment
and its archive/cache object. Full parent weights remain in the existing model
cache; no second parent weight copy is saved. No live service is changed.

The adapter format deliberately differs from the SDK's head-only save format.
This parent's encoder was tuned by its publisher; the SDK head-only loader would
load a different pretrained SmolVLM encoder. `vision_train.load_adapter` overlays
all and only decision-head tensors onto the exact full pinned parent and checks
the adapter hash and provenance. Old ModernBERT adapters are incompatible.

Six synthetic scene families are grouped into four train, one validation and
one test family. The policy templates recur and some core state contracts overlap
across scenes. This measures synthetic contract accuracy, not independent visual
navigation or autonomous improvement. Each held-out class has only two examples.
The visible result receipt records per-task/action accuracy, core overlap and
reversed-order behavior so a strong aggregate cannot hide a weak task.

Pixel learning needs immutable original pre-action screenshots, contemporaneous
public observations from the same owned client, exact original candidates,
independently verified outcomes and a complete no-assistance ledger. The
`admit_visual` gates reject stale/post-action frames, unknown intervention,
benchmark captures and synthetic/image pairings. Episode, site and client
lifetime groups must be held out together and repeated frames deduplicated.
These metadata gates must be followed by actual archive/hash and outcome review;
metadata declarations alone do not verify an outcome. Admitted visual SFT rows
still do not constitute on-policy RLVR. The two original benchmark captures are
not training labels. Promotion requires task-balanced held-out real visual
scenarios and unassisted live outcomes; this experiment cannot satisfy that gate.
