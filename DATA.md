# Data and evaluation record

TLC-RAPID does not include private experimental images in the source repository or Windows release. Input images under `user_input/images/` are ignored, and the release builder keeps only the placeholder instruction file.

## Required dataset description

Before manuscript submission, record the following for each dataset:

- Plate chemistry and manufacturer
- Imaging device, distance, exposure, resolution, illumination, and wavelength
- Number of plates, images, spots, compounds, and concentration levels
- Inclusion/exclusion criteria
- Annotation format and quality-control procedure
- Whether images from the same physical plate or experiment can occur in more than one split
- Fixed training, validation, and independent test manifests
- De-identification and permission/consent status where applicable

## Split policy

Thresholds and model choices must be selected using the training and validation sets only. The independent test set must remain untouched until the pipeline and all thresholds are locked. Split by physical plate or experimental batch, not merely by image crop, to reduce leakage.

## Public artifacts

Add the final dataset or controlled-access archive URL, DOI, license, and checksums here. If the raw images cannot be shared, provide at least a non-identifying example dataset, the frozen file manifests, annotations or aggregate ground truth, and the exact evaluation commands.
