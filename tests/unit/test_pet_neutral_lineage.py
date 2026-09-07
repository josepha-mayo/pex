"""Exercise pixel verification with real encoded media, including forged receipts."""

from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

_path = Path(__file__).resolve().parents[2] / "scripts" / "verify_pet_neutral_lineage.py"
_spec = importlib.util.spec_from_file_location("neutral_lineage", _path)
assert _spec and _spec.loader
lineage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lineage)


def encode(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, "WEBP", lossless=True, exact=True)
    return output.getvalue()


@pytest.fixture
def atlas_pair():
    before = Image.new("RGBA", (1536, 2288))
    before.putpixel((90, 80), (10, 50, 100, 255))
    after = before.copy()
    after.paste(before.crop((0, 0, 192, 208)), (1152, 0, 1344, 208))
    return before, after


def test_neutral_copy_proves_both_animation_hashes(atlas_pair):
    before, after = atlas_pair
    result = lineage.verify_pair(encode(before), encode(after))
    assert result["animation_pixels_sha256_before"] == result["animation_pixels_sha256_after"]
    assert result["before_sha256"] != result["after_sha256"]
    assert result["neutral_matches_idle_zero"] is True


@pytest.mark.parametrize(
    "pixel,error",
    [
        ((90, 80), "animation pixels changed"),
        ((1200, 80), "neutral slot does not exactly match"),
        ((1400, 80), "pixels outside the neutral copy changed"),
    ],
)
def test_change_outside_exact_copy_is_rejected(atlas_pair, pixel, error):
    before, after = atlas_pair
    after.putpixel(pixel, (100, 50, 10, 255))
    with pytest.raises(ValueError, match=error):
        lineage.verify_pair(encode(before), encode(after))


def test_receipt_cannot_use_a_mutable_or_option_ref(tmp_path):
    for value in ("HEAD", "--help", "a" * 39, None, "f" * 40):
        with pytest.raises(ValueError, match="full immutable Git commit|canonical baseline"):
            lineage.verify_lineage(tmp_path, value)
