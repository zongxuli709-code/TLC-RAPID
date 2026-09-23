# TLC-RAPID v1.0 submission and release checklist

## Automated release requirements

- [x] Public license is `AGPL-3.0-only`; the full text is in `LICENSE`.
- [x] The GUI and console expose copyright, no-warranty, license, and source
  notices.
- [x] `MODIFICATIONS.md` records the modified-work scope and dates.
- [x] `MODEL_WEIGHTS.md` records the weight hash, size, training metadata, and
  public-release license.
- [x] Direct dependency versions are pinned in `requirements-lock.txt`.
- [x] The fully resolved Windows build environment is recorded in
  `requirements-freeze.txt`.
- [x] Exact third-party license texts are collected in
  `THIRD_PARTY_LICENSES/`.
- [x] The release builder refuses a dirty or untagged source tree.
- [x] The release builder verifies the model hash and runs the unit tests.
- [x] The release builder produces a versioned GitHub source ZIP and a Windows
  x64 executable ZIP, each with `SOURCE_CODE.txt`, `VERSION.txt`, and an
  internal SHA-256 manifest.
- [x] Five anonymized workflow examples have per-image concentration mappings,
  a data license, and no embedded personal metadata.

## Author records still requiring confirmation

- [ ] Recover and record the exact starting Ultralytics YOLOv5 Git commit in
  `MODIFICATIONS.md` and `THIRD_PARTY_NOTICES.txt`. The current repository and
  stripped checkpoint do not contain it.
- [ ] Confirm the copyright owner(s), author spelling, affiliations, ORCID(s),
  repository URL, paper title, journal, DOI, and release date in `CITATION.cff`.
- [ ] Fill the dataset counts, sources, consent/privacy status, annotation
  protocol, split method, and public archive/DOI in `DATA.md`.
- [ ] Fill the final validation/test metrics and model-selection rule in
  `MODEL_CARD.md` and the manuscript.
- [ ] Confirm that every training/validation/test image and annotation can be
  legally shared under the data license stated in the archive.
- [ ] Have the dual-licensing plan reviewed by the institution's technology
  transfer office or qualified counsel before offering paid closed-source use.
  The public AGPL package itself cannot prohibit commercial use.

## Build and archive

After completing the author records, commit the release, place the exact
`v1.0` tag on that commit, and run:

```powershell
.\build_release.ps1
```

Expected outputs:

- `release/TLC-RAPID-v1.0-GitHub-source.zip`
- `release/TLC-RAPID-v1.0-Windows-user.zip`
- `release/SHA256SUMS.txt`

Upload both ZIP files and `SHA256SUMS.txt` to the same archival release page so
executable recipients have equivalent access to the corresponding source.
