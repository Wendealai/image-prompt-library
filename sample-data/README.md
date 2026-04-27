# Sample Data

Image Prompt Library does not commit runtime databases or user media. Optional sample data is provided as a curated bundle for screenshots, demos, and first-run exploration.

Sample installer command:

```bash
./scripts/install-sample-data.sh zh_hant
# or: ./scripts/install-sample-data.sh zh_hans
# or: ./scripts/install-sample-data.sh en
```

The manifests in `sample-data/manifests/` are kept in git. The image files are distributed separately as the `sample-data-v1` release asset `image-prompt-library-sample-images-v1.zip`, so normal clones stay lightweight.

Release asset SHA256:

```text
8a458f6c8c96079f40fbc46c689e7de0bd2eb464ee7f800f94f3ca60131d5035
```

The installer verifies the downloaded ZIP against this checksum before import. To test a local ZIP override with checksum verification, pass `SAMPLE_DATA_IMAGE_ZIP_SHA256=<sha256>` together with `SAMPLE_DATA_IMAGE_ZIP=...`.

For local QA without downloading from GitHub, point the installer at a local image ZIP:

```bash
IMAGE_PROMPT_LIBRARY_PATH=.local-work/sample-demo SAMPLE_DATA_IMAGE_ZIP=.local-work/image-prompt-library-sample-images-v1.zip ./scripts/install-sample-data.sh en
```

The current curated sample source is `wuyoscar/gpt_image_2_skill`. Preserve attribution and review the upstream license before publishing screenshots, demo GIFs, or release assets.
