from backend.services.use_case_classifier import classify_use_case


def test_classifier_prefers_use_case_specific_cluster_mapping():
    result = classify_use_case(
        title="Finance Dashboard",
        cluster_name="UI & Interfaces",
        tags=["dashboard"],
        prompt_texts=["A polished finance dashboard UI with charts"],
    )
    assert result.name == "界面设计"


def test_classifier_separates_poster_and_commercial_signals():
    poster = classify_use_case(
        title="Luxury Movie Poster",
        cluster_name="Photography & Realism",
        tags=["poster", "cinematic"],
        prompt_texts=["A cinematic poster with oversized title typography"],
    )
    commercial = classify_use_case(
        title="Beauty Brand Campaign",
        cluster_name="Fashion, Beauty & Lifestyle",
        tags=["beauty", "campaign"],
        prompt_texts=["A luxury beauty advertising campaign with glossy lighting"],
    )
    assert poster.name == "海报视觉"
    assert commercial.name == "商业广告"


def test_classifier_catches_people_and_spaces_without_legacy_clusters():
    portrait = classify_use_case(
        title="Studio Portrait Close-up",
        cluster_name=None,
        tags=["portrait"],
        prompt_texts=["A high-end studio portrait of a woman with soft lighting"],
    )
    scene = classify_use_case(
        title="Warm Minimal Living Room",
        cluster_name=None,
        tags=["interior"],
        prompt_texts=["A warm architectural interior living room scene with natural light"],
    )
    assert portrait.name == "人物肖像"
    assert scene.name == "场景空间"


def test_classifier_handles_social_ui_and_longform_info_cases():
    social = classify_use_case(
        title="杜甫朋友圈吐槽茅屋被掀翻",
        cluster_name="Other Use Cases",
        tags=["Social"],
        prompt_texts=["杜甫发朋友圈吐槽房顶被风刮没了"],
    )
    info = classify_use_case(
        title="户外活动通知信息长图",
        cluster_name=None,
        tags=["GPT Image 2"],
        prompt_texts=["路线、集合点、装备清单、注意事项都放在一张长图里"],
    )
    assert social.name == "界面设计"
    assert info.name == "信息图表"
