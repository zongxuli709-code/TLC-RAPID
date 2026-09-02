# TLC-RAPID licensing guide

This guide summarizes the intended release structure. It does not replace the
license texts and is not legal advice.

## Public research and open-source release

TLC-RAPID v1.0.0, including the bundled YOLOv5-derived inference code and the
published `best.pt` model, is distributed under the **GNU Affero General Public
License v3.0 only (AGPL-3.0-only)**. See `LICENSE`.

The AGPL permits academic, non-profit, government, and commercial use. A
recipient that distributes a modified or unmodified executable must also make
the complete corresponding source available under the AGPL. A modified version
must retain notices, state that it was modified, and give the relevant dates.
Users interacting with a modified version over a network must be offered its
corresponding source as required by AGPL section 13.

The public AGPL release therefore cannot impose an additional rule saying that
commercial use is forbidden or that a royalty is mandatory. Such a rule would
conflict with the rights already granted by the AGPL.

## Commercial or closed-source deployment

Organizations that do not want to satisfy the AGPL source-disclosure
obligations need separate written permissions from every necessary copyright
holder. In particular, the current product contains Ultralytics YOLO code and a
YOLO-trained model. Ultralytics states that proprietary deployment requires an
Ultralytics Enterprise License:

https://www.ultralytics.com/license

TLC-RAPID's authors may offer paid services, support, warranties, or a separate
license for material for which they hold the necessary rights. **This repository
does not grant a proprietary commercial license**, and an agreement with the
TLC-RAPID authors alone does not replace any license required from Ultralytics
or another third party.

Before advertising a paid closed-source TLC-RAPID license, obtain the necessary
upstream commercial rights and have the proposed commercial agreement reviewed
by qualified counsel.

## Components and artifacts

- TLC-RAPID combined source and executable: `AGPL-3.0-only`.
- `weights/best.pt`: distributed with the public release under
  `AGPL-3.0-only`; see `MODEL_WEIGHTS.md`.
- Third-party libraries: remain under their respective licenses; see
  `THIRD_PARTY_NOTICES.txt` and `THIRD_PARTY_LICENSES/`.
- Input images, experimental data, and analysis results are not automatically
  relicensed merely because TLC-RAPID processes them. Their owners must provide
  any permissions needed for publication or redistribution.

No trademark rights or endorsement rights are granted by the software license.

