import json
from pathlib import Path

from PIL import Image

from backend.db import connect, init_db
from backend.repositories import ItemRepository
from backend.services.import_awesome_gpt_image_2 import import_awesome_gpt_image_2, load_gallery_cases


def _write_gallery_fixture(root: Path) -> Path:
    docs = root / "docs"
    images = root / "data" / "images"
    docs.mkdir(parents=True)
    images.mkdir(parents=True)
    Image.new("RGB", (80, 60), "orange").save(images / "case310.jpg")
    Image.new("RGB", (60, 80), "blue").save(images / "case355.jpg")
    (docs / "gallery-part-2.md").write_text(
        """## Gallery

<a name="case-309"></a>

### 例 309：Should not import

![Should not import](../data/images/case309.jpg)

**提示词：**

```text
Skip me
```

***

<a name="case-310"></a>

### 例 310：零食品牌技术分解图

![零食品牌技术分解图](../data/images/case310.jpg)

**来源：** [@TechieBySA](https://x.com/TechieBySA/status/2031795709243019280)

**提示词：**

```text
[中文]
创建一个 [SNACK] 的品牌技术信息图。

[English]
Create a branded technical infographic of a [SNACK].
```

***

<a name="case-355"></a>

### 例 355：概念字体海报 Prompt

![概念字体海报 Prompt](../data/images/case355.jpg)

**来源：** [@dotey](https://x.com/dotey/status/2048793351290327381) / [Credit @xiaoxiaodong01](https://x.com/xiaoxiaodong01/status/2048443572119330853)

**提示词：**

```text
Create ONE finished premium conceptual typography poster for the exact title:

“[INPUT_TEXT]”
```

***
""",
        encoding="utf-8",
    )
    return root


def test_load_gallery_cases_parses_requested_range_with_curated_collections(tmp_path: Path):
    source = _write_gallery_fixture(tmp_path / "awesome-gpt-image-2")

    records = load_gallery_cases(source, start_case=310)

    assert [record["number"] for record in records] == [310, 355]
    first = records[0]
    assert first["title"] == "零食品牌技术分解图"
    assert first["collection_name"] == "图表与信息可视化"
    assert first["image"] == "data/images/case310.jpg"
    assert first["source_links"] == [{"label": "@TechieBySA", "url": "https://x.com/TechieBySA/status/2031795709243019280"}]
    assert first["case_url"].endswith("docs/gallery-part-2.md#case-310")
    prompts = {prompt.language: prompt.text for prompt in first["prompts"]}
    assert prompts["en"] == "Create a branded technical infographic of a [SNACK]."
    assert prompts["zh_hans"] == "创建一个 [SNACK] 的品牌技术信息图。"
    assert prompts["zh_hant"] == "創建一個 [SNACK] 的品牌技術信息圖。"
    assert records[1]["collection_name"] == "海报与排版"
    assert records[1]["author"] == "@dotey / Credit @xiaoxiaodong01"


def test_import_awesome_gpt_image_2_imports_images_prompts_and_is_idempotent(tmp_path: Path):
    source = _write_gallery_fixture(tmp_path / "awesome-gpt-image-2")
    library = tmp_path / "library"
    init_db(library)

    first = import_awesome_gpt_image_2(source, library, start_case=310)
    second = import_awesome_gpt_image_2(source, library, start_case=310)

    assert first.item_count == 2
    assert first.image_count == 2
    assert second.item_count == 0
    assert second.image_count == 0
    repo = ItemRepository(library)
    with connect(library) as conn:
        item_id = conn.execute("SELECT id FROM items WHERE slug=?", ("awesome-gpt-image-2-case-310",)).fetchone()[0]
    detail = repo.get_item(item_id)
    assert detail.cluster.name == "图表与信息可视化"
    assert detail.source_name == "freestylefly/awesome-gpt-image-2"
    assert detail.source_url.endswith("docs/gallery-part-2.md#case-310")
    assert detail.author == "@TechieBySA"
    assert detail.images and (library / detail.images[0].thumb_path).exists()
    assert "MIT" in (detail.notes or "")
    assert "https://x.com/TechieBySA/status/2031795709243019280" in (detail.notes or "")
    prompt_languages = {prompt.language for prompt in detail.prompts}
    assert prompt_languages == {"en", "zh_hans", "zh_hant"}
    assert repo.list_items(limit=10).total == 2
