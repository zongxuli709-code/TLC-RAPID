# TLC-RAPID model card

## Model overview

TLC-RAPID uses a custom Ultralytics YOLOv5 segmentation model to locate TLC spots before image-based quantification. The expected model file is `weights/best.pt`.

- Architecture family: YOLOv5 segmentation
- Intended task: TLC spot instance segmentation
- Supported image profiles: visible light, 254 nm, and 366 nm fluorescence
- TLC-RAPID v1.0.0 weight SHA-256: `E507240E8C7BB8E8C3C57ABB20ADEE6FEBA78670F2EDF6E06BCF1AE12A4440A5`
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

## Information required before manuscript submission

Complete the following from the final experimental records:

- Training/validation/test image counts and plate sources
- Annotation protocol and annotator agreement
- Exact upstream YOLOv5 repository commit and pretrained checkpoint
- Training command, hyperparameters, augmentations, epochs, image size, batch size, seed, and hardware
- Validation-set model selection rule
- Independent test-set Precision, Recall, F1, mask IoU, and mAP
- Data and weight licenses, public archive URL, and DOI if available

The checkpoint's recoverable training settings and its public-release license
are documented in [MODEL_WEIGHTS.md](MODEL_WEIGHTS.md). The upstream Git commit,
dataset counts, annotation provenance, final selected epoch, and validation/test
metrics were not stored in the stripped checkpoint and must be recovered from
the laboratory records rather than guessed.

## Provenance

The model file hash is written to every result workbook's `Metadata` sheet. A hash mismatch means the result was produced with a different model and should be treated as a separate software/model version.
