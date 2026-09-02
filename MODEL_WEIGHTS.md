# Model weights and licensing

## Released artifact

- File: `weights/best.pt`
- TLC-RAPID release: v1.0.0
- SHA-256: `E507240E8C7BB8E8C3C57ABB20ADEE6FEBA78670F2EDF6E06BCF1AE12A4440A5`
- Size: 15,361,187 bytes
- Checkpoint timestamp metadata: `2025-04-29T19:05:58.850629`
- Format: PyTorch checkpoint containing a YOLOv5 segmentation model
- Architecture: YOLOv5s-seg family, 27 classes, input image size 640 used for
  training, strides 8/16/32
- Initial checkpoint recorded by the training options: `yolov5s-seg.pt`

## License

The model was trained with Ultralytics YOLOv5. For this public release, the
checkpoint is provided under **GNU AGPL v3 only (AGPL-3.0-only)** together with
the complete TLC-RAPID source package. Ultralytics states that its trained YOLO
models are AGPL-3.0 by default and that proprietary use requires an Enterprise
License. See `LICENSING.md`.

No separate permission for closed-source or proprietary commercial deployment
is granted with this weight file. Removing the file from its accompanying
source package does not remove the applicable license obligations.

## Provenance recorded in the checkpoint

The checkpoint preserves these training options:

- epochs requested: 1000; early-stopping patience: 100
- batch size: 16
- image size: 640
- optimizer: SGD
- seed: 0
- device: CUDA device 0
- mask ratio: 4
- augmentation: HSV, translation 0.1, scale 0.5, horizontal flip 0.5,
  mosaic 1.0; no mixup or copy-paste
- upstream Git remote/branch/commit: not recorded (`None`)

The checkpoint was stripped for inference: its stored epoch is `-1`, and it
does not contain final validation metrics, dataset counts, label provenance, or
the exact upstream source commit. Those facts must come from the laboratory's
training records and should be reported with the manuscript. See `MODEL_CARD.md`
and `DATA.md`.

## Integrity check

On Windows PowerShell:

```powershell
Get-FileHash .\weights\best.pt -Algorithm SHA256
```

Do not use a weight file whose hash differs from the value above without
recording it as a different model release.

