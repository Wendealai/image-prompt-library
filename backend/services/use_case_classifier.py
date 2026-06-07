from __future__ import annotations

from dataclasses import dataclass


USE_CASES = [
    "界面设计",
    "信息图表",
    "产品电商",
    "品牌包装",
    "海报视觉",
    "商业广告",
    "角色IP",
    "人物肖像",
    "场景空间",
    "艺术插画",
    "其他",
]

USE_CASE_ORDER = {name: index for index, name in enumerate(USE_CASES)}

LEGACY_CLUSTER_MAP: dict[str, str] = {
    "ui & interfaces": "界面设计",
    "ui与界面": "界面设计",
    "photography & real-world screens": "界面设计",
    "图表与信息可视化": "信息图表",
    "technical & research diagrams": "信息图表",
    "education & infographics": "信息图表",
    "charts & infographics": "信息图表",
    "海报与排版": "海报视觉",
    "posters & typography": "海报视觉",
    "design, posters & typography": "海报视觉",
    "products & e-commerce": "产品电商",
    "商品与电商": "产品电商",
    "brand & logos": "品牌包装",
    "品牌与标志": "品牌包装",
    "characters & anime": "角色IP",
    "人物与角色": "角色IP",
    "illustration & art": "艺术插画",
    "插画与艺术": "艺术插画",
    "art & illustration": "艺术插画",
    "cinematic storytelling": "场景空间",
    "scenes & storytelling": "场景空间",
    "场景与叙事": "场景空间",
    "architecture & interiors": "场景空间",
}

USE_CASE_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "界面设计": {
        "strong": ("ui", "interface", "dashboard", "landing page", "mobile app", "website", "web app", "saas", "wireframe", "x page", "wechat moments", "douyin", "social profile", "仪表盘", "界面", "后台", "网页", "落地页", "应用界面", "朋友圈", "抖音", "社交页面", "直播页面"),
        "support": ("screen", "ios", "android", "figma", "product page ui", "feed", "profile page", "timeline", "组件", "页面", "交互", "控件", "动态", "直播", "个人主页"),
    },
    "信息图表": {
        "strong": ("infographic", "diagram", "chart", "data visualization", "data visualisation", "flowchart", "timeline", "schema", "technical", "research", "exploded assembly drawing", "newspaper", "notice", "guide", "manual", "信息图", "图表", "信息可视化", "流程图", "时间线", "科研", "技术图", "示意图", "数据", "拆解图", "说明书", "日报", "长图", "通知", "路线图"),
        "support": ("map", "blueprint", "annotation", "checklist", "装备清单", "集合点", "注意事项", "标注", "结构图", "可视化"),
    },
    "产品电商": {
        "strong": ("e-commerce", "ecommerce", "marketplace", "packshot", "listing", "product shot", "product render", "amazon", "catalog", "shop", "电商", "商品", "产品图", "主图", "详情页", "白底产品"),
        "support": ("product", "bottle", "watch", "shoe", "bag", "cosmetic product", "瓶子", "鞋", "包", "手袋", "电商图"),
    },
    "品牌包装": {
        "strong": ("branding", "brand identity", "logo", "packaging", "package design", "label design", "visual identity", "品牌", "标志", "logo设计", "包装", "包装设计", "标签设计", "视觉识别", "vi"),
        "support": ("box", "label", "identity system", "盒子", "罐", "袋装", "瓶标"),
    },
    "海报视觉": {
        "strong": ("poster", "typography", "movie poster", "album cover", "magazine cover", "flyer", "title treatment", "calendar", "postcard", "sign design", "hand-held sign", "海报", "排版", "字体设计", "封面", "杂志封面", "电影海报", "专辑封面", "日历", "明信片", "手举牌"),
        "support": ("cover", "billboard", "print design", "平面设计", "字效", "长卷文字版"),
    },
    "商业广告": {
        "strong": ("advertising", "advertisement", "campaign", "commercial", "promo", "promotion", "beauty shot", "fashion campaign", "brand campaign", "social ad", "广告", "商业", "宣传", "宣发", "品宣", "美妆大片", "时尚大片", "商业摄影"),
        "support": ("editorial", "launch", "marketing", "luxury ad", "editorial shoot", "营销", "大片"),
    },
    "角色IP": {
        "strong": ("character", "anime", "mascot", "avatar", "figurine", "chibi", "cartoon", "comic", "monster", "creature", "pixar", "fps game", "valorant", "角色", "动漫", "二次元", "吉祥物", "手办", "卡通", "漫画", "玩偶", "ip", "游戏世界", "游戏设定"),
        "support": ("toy", "lego", "clay", "sticker", "doll", "乐高", "黏土", "贴纸"),
    },
    "人物肖像": {
        "strong": ("portrait", "headshot", "selfie", "beauty portrait", "fashion portrait", "close-up face", "red-dressed woman", "人像", "肖像", "面部", "半身照", "证件照", "妆容", "模特", "女子", "红妆"),
        "support": ("woman", "man", "girl", "boy", "face", "beauty", "person", "people", "女性", "男性", "女孩", "男孩", "人物", "美人"),
    },
    "场景空间": {
        "strong": ("interior", "architecture", "building", "room", "living room", "bedroom", "office", "street", "cityscape", "landscape", "cinematic scene", "environment", "palace", "imperial palace", "室内", "建筑", "空间", "街景", "城市", "风景", "场景", "客厅", "卧室", "办公室", "皇宫"),
        "support": ("subway", "cafe", "restaurant", "store interior", "villa", "house", "garden", "flower field", "自然景观", "地铁", "咖啡馆", "餐厅", "店铺", "房屋", "花丛"),
    },
    "艺术插画": {
        "strong": ("illustration", "painting", "watercolor", "collage", "sketch", "concept art", "hand-drawn", "oil painting", "scroll painting", "authentic picture", "插画", "绘画", "水彩", "拼贴", "草图", "手绘", "概念艺术", "油画", "长卷图", "意境图", "真迹", "复刻"),
        "support": ("abstract", "surreal", "doodle", "print art", "诗词", "古诗", "抽象", "超现实", "涂鸦", "版画"),
    },
}


@dataclass(frozen=True)
class UseCaseClassification:
    name: str
    score: int
    reasons: tuple[str, ...] = ()


def normalize_use_case_name(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def use_case_sort_key(value: str) -> tuple[int, str]:
    return (USE_CASE_ORDER.get(value, len(USE_CASE_ORDER)), value)


def _normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _score_keywords(text: str, keywords: tuple[str, ...], weight: int) -> int:
    score = 0
    for keyword in keywords:
        if keyword and keyword in text:
            score += weight
    return score


def classify_use_case(
    *,
    title: str,
    cluster_name: str | None = None,
    tags: list[str] | None = None,
    prompt_texts: list[str] | None = None,
) -> UseCaseClassification:
    title_text = _normalize_text(title)
    cluster_text = _normalize_text(cluster_name)
    tag_text = " ".join(_normalize_text(tag) for tag in (tags or []))
    prompt_text = " ".join(_normalize_text(prompt) for prompt in (prompt_texts or []))
    combined = " ".join(part for part in (title_text, cluster_text, tag_text, prompt_text) if part)

    if cluster_text in LEGACY_CLUSTER_MAP:
        mapped = LEGACY_CLUSTER_MAP[cluster_text]
        return UseCaseClassification(name=mapped, score=120, reasons=(f"cluster:{cluster_name}",))

    if not combined:
        return UseCaseClassification(name="其他", score=0)

    scores: dict[str, int] = {name: 0 for name in USE_CASES}
    reasons: dict[str, list[str]] = {name: [] for name in USE_CASES}

    for name, groups in USE_CASE_RULES.items():
        strong = groups.get("strong", ())
        support = groups.get("support", ())
        title_score = _score_keywords(title_text, strong, 16) + _score_keywords(title_text, support, 7)
        cluster_score = _score_keywords(cluster_text, strong, 18) + _score_keywords(cluster_text, support, 8)
        tag_score = _score_keywords(tag_text, strong, 12) + _score_keywords(tag_text, support, 6)
        prompt_score = _score_keywords(prompt_text, strong, 8) + _score_keywords(prompt_text, support, 3)
        total = title_score + cluster_score + tag_score + prompt_score
        if total:
            scores[name] += total
            reasons[name].append(f"score:{total}")

    if "poster" in combined or "海报" in combined:
        scores["海报视觉"] += 14
    if "calendar" in combined or "日历" in combined or "postcard" in combined or "明信片" in combined:
        scores["海报视觉"] += 12
    if "newspaper" in combined or "日报" in combined or "长图" in combined or "拆解图" in combined or "infographic" in combined or "信息长图" in combined:
        scores["信息图表"] += 14
    if "朋友圈" in combined or "x page" in combined or "抖音直播" in combined or "live stream" in combined or "livestream" in combined:
        scores["界面设计"] += 15
    if "campaign" in combined or "广告" in combined or "commercial" in combined:
        scores["商业广告"] += 10
    if ("product" in combined or "商品" in combined or "电商" in combined) and ("poster" not in combined and "海报" not in combined):
        scores["产品电商"] += 8
    if "character" in combined or "角色" in combined or "anime" in combined or "动漫" in combined:
        scores["角色IP"] += 9
    if "fps" in combined or "valorant" in combined or "游戏世界" in combined:
        scores["角色IP"] += 14
    if "portrait" in combined or "人像" in combined or "肖像" in combined:
        scores["人物肖像"] += 10
    if "女子" in combined or "红妆" in combined:
        scores["人物肖像"] += 12
    if "长卷图" in combined or "意境图" in combined or "真迹" in combined or "复刻" in combined:
        scores["艺术插画"] += 14

    ranked = sorted(
        ((name, score) for name, score in scores.items() if name != "其他"),
        key=lambda item: (-item[1], use_case_sort_key(item[0])),
    )
    if not ranked or ranked[0][1] <= 0:
        return UseCaseClassification(name="其他", score=0)
    best_name, best_score = ranked[0]
    return UseCaseClassification(name=best_name, score=best_score, reasons=tuple(reasons[best_name]))
