from backend.services.prompt_source_prepare import prepare_prompt_template_source


def test_prepare_prompt_template_source_extracts_labelled_tail_prompt():
    wrapped = (
        "Here's how to create your Whiteboard Animation style image.\n\n"
        "Use Google Nano Banana Pro or any other AI image generation model.\n\n"
        "Use this prompt: clean whiteboard animation style illustration of the person from the reference image, "
        "drawn as a simple black marker sketch on a pure white background."
    )

    prepared = prepare_prompt_template_source(wrapped)

    assert prepared.was_extracted is True
    assert prepared.strategy == "labelled_tail"
    assert prepared.normalized_text == (
        "clean whiteboard animation style illustration of the person from the reference image, "
        "drawn as a simple black marker sketch on a pure white background."
    )


def test_prepare_prompt_template_source_extracts_labelled_chinese_prompt():
    wrapped = (
        "下面是可直接复用的版本。\n\n"
        "提示词：请基于我上传的人像照片，生成一张竖版 3:4 的高级极简海报，保留人物身份特征，"
        "将背景替换为干净的灰白色渐变，并加入精致排版。"
    )

    prepared = prepare_prompt_template_source(wrapped)

    assert prepared.was_extracted is True
    assert prepared.normalized_text == (
        "请基于我上传的人像照片，生成一张竖版 3:4 的高级极简海报，保留人物身份特征，"
        "将背景替换为干净的灰白色渐变，并加入精致排版。"
    )


def test_prepare_prompt_template_source_keeps_plain_prompt_intact():
    raw = "A cinematic poster of a tiny ramen bar with paper lanterns and wooden stools."

    prepared = prepare_prompt_template_source(raw)

    assert prepared.was_extracted is False
    assert prepared.strategy == "original"
    assert prepared.normalized_text == raw
