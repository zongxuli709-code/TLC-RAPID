# TLC-RAPID model card

## Model overview

TLC-RAPID uses a custom Ultralytics YOLOv5 segmentation model to locate TLC spots before image-based quantification. The expected model file is `weights/best.pt`.

- Architecture family: YOLOv5 segmentation
- Intended task: TLC spot instance segmentation
- Supported image profiles: visible light, 254 nm, and 366 nm fluorescence
- TLC-RAPID v1.0 weight SHA-256: `E507240E8C7BB8E8C3C57ABB20ADEE6FEBA78670F2EDF6E06BCF1AE12A4440A5`
- File size: 15,361,187 bytes
- Model classes: 27
- Training input size: 640 pixels
- Training checkpoint date: 2025-04-29

## Intended use

The model is intended for research use on TLC plate images acquired under conditions represented in the training and validation data. Quantitative results must be checked against standards on the same plate and must not be treated as clinical or regulatory measurements without an independent validation.

## Known limitations

- Performance can change with illumination, camera, plate type, crop, rotation, background, and spot morphology.
- A missed detection cannot currently be manually added when an image has zero automatic detections.
- Manual marking changes the final spot list and must be reported when used.
- Concentrations outside the standard-response range are flagged and should not be interpreted as validated measurements.

## Evaluation and missing provenance

- Development collection reported in the manuscript: approximately 1,000 images.
- Independent test subset: 82 images, 745 target bands, TP=711, FP=6, FN=34.
- Independent-test precision: 99.16%; recall: 95.44%; F1-score: 97.26%.
- Recoverable training settings: 1,000 requested epochs, patience 100, batch 16,
  image size 640, SGD, seed 0, CUDA device 0, and the augmentations listed in
  `MODEL_WEIGHTS.md`.
- Not recoverable from the stripped checkpoint or repository: exact upstream
  YOLOv5 commit, final selected epoch, training/validation manifests, plate
  grouping, annotator agreement, mask IoU, mAP, and validation selection rule.
- The development and independent-test images have no public DOI or archive in
  this release. The five bundled images are workflow examples, not test data.

The checkpoint's recoverable training settings and its public-release license
are documented in [MODEL_WEIGHTS.md](MODEL_WEIGHTS.md). The upstream Git commit,
dataset counts, annotation provenance, final selected epoch, and validation/test
metrics were not stored in the stripped checkpoint and must be recovered from
the laboratory records rather than guessed.

## Provenance

The model file hash is written to every result workbook's `Metadata` sheet. A hash mismatch means the result was produced with a different model and should be treated as a separate software/model version.
