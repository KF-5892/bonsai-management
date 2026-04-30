"""画像処理サービス。

- 元画像（長辺 2048px 超ならリサイズして上書き）
- 中サイズ（長辺 1080px、JPEG q=85）
- サムネ（長辺 320px、JPEG q=85）

EXIF 回転を考慮し、PNG など他フォーマットは JPEG に統一する。
透明背景のあるフォーマットは白背景に合成する。
"""

from __future__ import annotations

import contextlib
import os
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models.fields.files import ImageFieldFile
from PIL import Image, ImageOps

JPEG_QUALITY = 85
JPEG_EXT = ".jpg"


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    """透明背景を白で合成して RGB に変換する。"""
    if image.mode == "RGB":
        return image
    if image.mode in ("RGBA", "LA"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        alpha = image.split()[-1]
        rgb = image.convert("RGBA")
        background.paste(rgb, mask=alpha)
        return background
    if image.mode == "P":
        # パレット画像は RGBA に変換してから合成
        return _flatten_to_rgb(image.convert("RGBA"))
    return image.convert("RGB")


def _resize_long_edge(image: Image.Image, long_edge: int) -> Image.Image:
    """長辺が `long_edge` px を超える場合のみ縮小する。"""
    width, height = image.size
    current = max(width, height)
    if current <= long_edge:
        return image
    scale = long_edge / current
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _to_jpeg_content_file(image: Image.Image, base_name: str, suffix: str) -> ContentFile:
    """`Image` を JPEG にエンコードして `ContentFile` として返す。"""
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    buf.seek(0)
    stem, _ext = os.path.splitext(os.path.basename(base_name))
    file_name = f"{stem}_{suffix}{JPEG_EXT}"
    return ContentFile(buf.getvalue(), name=file_name)


def generate_variants(
    image_field_file: ImageFieldFile,
) -> tuple[ContentFile | None, ContentFile | None]:
    """元画像から中サイズ・サムネイルの `ContentFile` を生成する。

    - `image_field_file` の中身を Pillow で開き、EXIF 回転を適用
    - 元画像が長辺 `BONSAI_IMAGE_MAX_LONG_EDGE` を超える場合は
      JPEG で再エンコードして元の `ImageFieldFile` を上書き保存する
    - 中・サムネを JPEG `ContentFile` として返す

    Returns:
        (medium_file, thumbnail_file) のタプル。
        画像を開けなかった場合などは `(None, None)`。
    """
    if not image_field_file:
        return None, None

    max_long_edge: int = getattr(settings, "BONSAI_IMAGE_MAX_LONG_EDGE", 2048)
    variants: dict[str, int] = getattr(
        settings,
        "BONSAI_IMAGE_VARIANTS",
        {"medium": 1080, "thumbnail": 320},
    )
    medium_edge = variants.get("medium", 1080)
    thumb_edge = variants.get("thumbnail", 320)

    try:
        image_field_file.open("rb")
        with Image.open(image_field_file) as raw:
            raw.load()
            oriented = ImageOps.exif_transpose(raw) or raw
            base_image = _flatten_to_rgb(oriented)
    except (OSError, ValueError, Image.UnidentifiedImageError):
        return None, None
    finally:
        with contextlib.suppress(Exception):
            image_field_file.close()

    base_name = os.path.basename(getattr(image_field_file, "name", "image.jpg"))

    # 元画像のリサイズ（必要なら上書き）
    width, height = base_image.size
    if max(width, height) > max_long_edge:
        resized_original = _resize_long_edge(base_image, max_long_edge)
        original_cf = _to_jpeg_content_file(resized_original, base_name, "original")
        # ImageFieldFile を差し替える（save=False。呼び出し元で全体を save する）
        image_field_file.save(original_cf.name, original_cf, save=False)
        source_for_variants = resized_original
    else:
        source_for_variants = base_image

    medium_image = _resize_long_edge(source_for_variants, medium_edge)
    thumb_image = _resize_long_edge(source_for_variants, thumb_edge)

    medium_cf = _to_jpeg_content_file(medium_image, base_name, "medium")
    thumb_cf = _to_jpeg_content_file(thumb_image, base_name, "thumb")
    return medium_cf, thumb_cf
