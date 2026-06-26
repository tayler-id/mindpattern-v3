from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_fly_image_copies_core_package() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text()

    assert "COPY core/ core/" in dockerfile
