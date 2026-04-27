# Sample Data

Image Prompt Library does not commit runtime databases or user media. Optional sample data is provided as a curated bundle for screenshots, demos, and first-run exploration.

Sample installer command:

```bash
./scripts/install-sample-data.sh zh_hant
# or: ./scripts/install-sample-data.sh zh_hans
# or: ./scripts/install-sample-data.sh en
```

The manifests in `sample-data/manifests/` are kept in git. The image files are distributed separately as the GitHub Release asset `sample-data-v1` / `image-prompt-library-sample-images-v1.zip`, so normal clones stay lightweight. While the repository remains private, the installer's unauthenticated `curl` download may return 404; re-test the command after switching the repository public.

For local QA without downloading from GitHub, point the installer at a local image ZIP:

```bash
IMAGE_PROMPT_LIBRARY_PATH=.local-work/sample-demo SAMPLE_DATA_IMAGE_ZIP=.local-work/image-prompt-library-sample-images-v1.zip ./scripts/install-sample-data.sh en
```

The current curated sample source is `wuyoscar/gpt_image_2_skill`. Preserve attribution and review the upstream license before publishing screenshots, demo GIFs, or release assets.
