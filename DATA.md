# Data and evaluation record

TLC-RAPID does not include private experimental images in the source repository or releases. Input images under `user_input/images/` are ignored by Git.

## Bundled workflow example

One anonymized demonstration image is distributed in `example_data/` with
its per-image standard applied amounts and an explicit data license. The
release builder copies it into `user_input/` so a new user can run the
workflow immediately. It is not part of the training, validation, or
independent test sets and must not be used as a performance benchmark. See
`example_data/README.md` and `example_data/DATA_LICENSE.txt`.

## Dataset record

The manuscript reports a development collection of approximately 1,000 TLC
images: approximately 500 visible-light, 350 at 366 nm, and 150 at 254 nm.
Target-band boundaries were annotated manually with LabelMe and converted to
the YOLO segmentation format.

The independent standard test subset contains 82 images and 745 manually
verified target bands: 31 visible-light images, 37 at 366 nm, and 14 at 254 nm.
At confidence 0.15, the reported totals are TP=711, FP=6, and FN=34
(precision 99.16%, recall 95.44%, F1 97.26%).

The repository does not contain the laboratory manifests needed to verify the
training/validation split, physical-plate grouping, acquisition settings, or
whether images from one physical plate occur in more than one split. These
facts remain unavailable and must not be inferred from image counts.

## Split policy

Thresholds and model choices must be selected using the training and validation sets only. The independent test set must remain untouched until the pipeline and all thresholds are locked. Split by physical plate or experimental batch, not merely by image crop, to reduce leakage.

## Public artifacts

No public archive or DOI is currently available for the development and test
datasets. The release provides only one non-identifying workflow example,
its applied-amount mapping, aggregate independent-test ground truth, and the
evaluation commands in `REPRODUCIBILITY.md`.

Four earlier workflow images that do not pass the default quadratic
invertibility check remain in the source tree for diagnosis. They have no
active release concentration mapping and are not copied into the Windows user
package.
