import httpx
from fastapi.testclient import TestClient
from io import BytesIO
from PIL import Image

from backend.main import create_app
from backend.schemas import CaseIntakeFetchResult
from backend.services.case_intake import FetchedCaseImage, fetch_case_image_from_url, fetch_case_intake_from_url


def test_fetch_case_intake_from_url_extracts_structured_html():
    def handler(request: httpx.Request) -> httpx.Response:
        html = """
        <html>
          <head>
            <title>Glass Teahouse Hero</title>
            <meta name="description" content="Campaign landing page visual.">
            <meta name="author" content="Edward">
            <meta property="og:image" content="/media/hero-shot.jpg">
            <meta name="twitter:image" content="https://cdn.example.test/social-card.webp">
          </head>
          <body>
            <main>
              <img src="/media/hero-shot.jpg" alt="Duplicate hero">
              <img src="./details.png" alt="Detail crop">
              <h1>Glass Teahouse Hero</h1>
              <h2>English Prompt</h2>
              <p>A dreamy glass teahouse hero shot with soft morning mist.</p>
              <h2>Tags</h2>
              <p>glass, mist, cinematic</p>
            </main>
          </body>
        </html>
        """
        return httpx.Response(200, text=html, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        result = fetch_case_intake_from_url("https://example.test/case", client=client)

    assert result.url == "https://example.test/case"
    assert result.final_url == "https://example.test/case"
    assert result.title == "Glass Teahouse Hero"
    assert result.description == "Campaign landing page visual."
    assert result.author == "Edward"
    assert result.image_url == "https://example.test/media/hero-shot.jpg"
    assert [candidate.url for candidate in result.image_candidates] == [
        "https://example.test/media/hero-shot.jpg",
        "https://cdn.example.test/social-card.webp",
        "https://example.test/details.png",
    ]
    assert [candidate.source for candidate in result.image_candidates] == ["open_graph", "twitter", "body"]
    assert result.image_candidates[2].alt == "Detail crop"
    assert "Title: Glass Teahouse Hero" in result.intake_text
    assert "Source URL: https://example.test/case" in result.intake_text
    assert "Notes:\nCampaign landing page visual." in result.intake_text
    assert "English Prompt" in result.intake_text
    assert "A dreamy glass teahouse hero shot with soft morning mist." in result.intake_text
    assert "Tags\nglass, mist, cinematic" in result.intake_text


def test_case_intake_fetch_endpoint_returns_service_payload(tmp_path, monkeypatch):
    client = TestClient(create_app(library_path=tmp_path / "library"))

    def fake_fetch(url: str) -> CaseIntakeFetchResult:
        assert url == "https://example.test/case"
        return CaseIntakeFetchResult(
            url=url,
            final_url=url,
            title="Fetched title",
            description="Fetched description",
            author="Fetched author",
            image_url="https://example.test/image.jpg",
            image_candidates=[{"url": "https://example.test/image.jpg", "source": "open_graph", "alt": None}],
            intake_text="Title: Fetched title\nSource URL: https://example.test/case",
        )

    monkeypatch.setattr("backend.routers.intake.fetch_case_intake_from_url", fake_fetch)

    response = client.post("/api/intake/fetch", json={"url": "https://example.test/case"})

    assert response.status_code == 200
    assert response.json() == {
        "url": "https://example.test/case",
        "final_url": "https://example.test/case",
        "title": "Fetched title",
        "description": "Fetched description",
        "author": "Fetched author",
        "image_url": "https://example.test/image.jpg",
        "image_candidates": [{"url": "https://example.test/image.jpg", "source": "open_graph", "alt": None}],
        "intake_text": "Title: Fetched title\nSource URL: https://example.test/case",
    }


def test_case_intake_fetch_endpoint_rejects_invalid_url(tmp_path):
    client = TestClient(create_app(library_path=tmp_path / "library"))

    response = client.post("/api/intake/fetch", json={"url": "ftp://example.test/case"})

    assert response.status_code == 400
    assert response.text


def test_fetch_case_image_from_url_returns_verified_image_payload():
    image = Image.new("RGB", (16, 12), (120, 80, 200))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    payload = buffer.getvalue()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={"content-type": "image/png"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        fetched = fetch_case_image_from_url("https://example.test/reference", client=client)

    assert fetched.url == "https://example.test/reference"
    assert fetched.final_url == "https://example.test/reference"
    assert fetched.content_type == "image/png"
    assert fetched.filename.endswith(".png")
    assert fetched.data == payload


def test_case_intake_image_endpoint_returns_image_proxy(tmp_path, monkeypatch):
    client = TestClient(create_app(library_path=tmp_path / "library"))

    def fake_fetch(url: str) -> FetchedCaseImage:
        assert url == "https://example.test/reference.png"
        return FetchedCaseImage(
            url=url,
            final_url=url,
            filename="reference.png",
            content_type="image/png",
            data=b"fakepng",
        )

    monkeypatch.setattr("backend.routers.intake.fetch_case_image_from_url", fake_fetch)

    response = client.get("/api/intake/image", params={"url": "https://example.test/reference.png"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.headers["x-intake-filename"] == "reference.png"
    assert response.content == b"fakepng"
