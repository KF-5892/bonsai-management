"""地域（都道府県）と、見ごろの時期を補正するための気候区分。

見ごろは品種ごとに「基準値」（関東〜九州の平野部）を 1 つだけ持ち、
地域差は気候区分ごとの「旬のずれ」で補正する。47 都道府県ごとにデータを
持たないのは、時期を決めているのが行政区分ではなく気温だから
（県内の差は残り、隣接県はほぼ同じ値になる）。

ずれの値は気象庁 生物季節観測の平年値（東京との差）を旬に丸めたもの:

- 春の花   … さくらの開花日（1991〜2020 年平年値）
- 紅葉・実 … かえでの紅葉日（観測日と平年差からの逆算）
- 冬の花   … うめの開花日（同上）。道北・道東は観測値が無く、道央・道南に
  さくらと同じ差（+1 旬）を足した推定値

旬は 1 年を 36 個に分けた単位（各月の上旬・中旬・下旬）。
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class Region(models.TextChoices):
    """ユーザーが選ぶ地域。都道府県単位だが、北海道だけ 2 つに分ける。"""

    HOKKAIDO_SW = "hokkaido_sw", _("北海道（道央・道南）")
    HOKKAIDO_NE = "hokkaido_ne", _("北海道（道北・道東）")
    AOMORI = "aomori", _("青森県")
    IWATE = "iwate", _("岩手県")
    MIYAGI = "miyagi", _("宮城県")
    AKITA = "akita", _("秋田県")
    YAMAGATA = "yamagata", _("山形県")
    FUKUSHIMA = "fukushima", _("福島県")
    IBARAKI = "ibaraki", _("茨城県")
    TOCHIGI = "tochigi", _("栃木県")
    GUNMA = "gunma", _("群馬県")
    SAITAMA = "saitama", _("埼玉県")
    CHIBA = "chiba", _("千葉県")
    TOKYO = "tokyo", _("東京都")
    KANAGAWA = "kanagawa", _("神奈川県")
    NIIGATA = "niigata", _("新潟県")
    TOYAMA = "toyama", _("富山県")
    ISHIKAWA = "ishikawa", _("石川県")
    FUKUI = "fukui", _("福井県")
    YAMANASHI = "yamanashi", _("山梨県")
    NAGANO = "nagano", _("長野県")
    GIFU = "gifu", _("岐阜県")
    SHIZUOKA = "shizuoka", _("静岡県")
    AICHI = "aichi", _("愛知県")
    MIE = "mie", _("三重県")
    SHIGA = "shiga", _("滋賀県")
    KYOTO = "kyoto", _("京都府")
    OSAKA = "osaka", _("大阪府")
    HYOGO = "hyogo", _("兵庫県")
    NARA = "nara", _("奈良県")
    WAKAYAMA = "wakayama", _("和歌山県")
    TOTTORI = "tottori", _("鳥取県")
    SHIMANE = "shimane", _("島根県")
    OKAYAMA = "okayama", _("岡山県")
    HIROSHIMA = "hiroshima", _("広島県")
    YAMAGUCHI = "yamaguchi", _("山口県")
    TOKUSHIMA = "tokushima", _("徳島県")
    KAGAWA = "kagawa", _("香川県")
    EHIME = "ehime", _("愛媛県")
    KOCHI = "kochi", _("高知県")
    FUKUOKA = "fukuoka", _("福岡県")
    SAGA = "saga", _("佐賀県")
    NAGASAKI = "nagasaki", _("長崎県")
    KUMAMOTO = "kumamoto", _("熊本県")
    OITA = "oita", _("大分県")
    MIYAZAKI = "miyazaki", _("宮崎県")
    KAGOSHIMA = "kagoshima", _("鹿児島県")
    OKINAWA = "okinawa", _("沖縄県")


class ClimateZone(models.TextChoices):
    """見ごろの補正に使う気候区分。"""

    HOKKAIDO_NE = "hokkaido_ne", _("北海道（道北・道東）")
    HOKKAIDO_SW = "hokkaido_sw", _("北海道（道央・道南）")
    TOHOKU_NORTH = "tohoku_north", _("東北北部")
    TOHOKU_SOUTH = "tohoku_south", _("東北南部・新潟・長野")
    HOKURIKU = "hokuriku", _("北陸")
    STANDARD = "standard", _("関東〜九州の平野部")
    OKINAWA = "okinawa", _("沖縄")


class ClimateAdjust(models.IntegerChoices):
    """同じ気候区分のなかでの微調整（高原・山間部など）。"""

    WARMER = -1, _("暖かい場所（春は1旬早く、秋は1旬遅く）")
    NONE = 0, _("補正しない")
    COLDER = 1, _("寒い場所・高原や山間部（春は1旬遅く、秋は1旬早く）")


class ViewingShift(models.TextChoices):
    """見ごろが寒い地域でどちらへ動くかの型。"""

    SPRING = "spring", _("春の花（寒い地域ほど遅い）")
    AUTUMN = "autumn", _("紅葉・実（寒い地域ほど早い）")
    WINTER = "winter", _("冬〜早春の花（寒い地域ほど大きく遅れる）")
    NONE = "none", _("地域差を補正しない")


_REGION_ZONES: dict[str, ClimateZone] = {
    Region.HOKKAIDO_NE: ClimateZone.HOKKAIDO_NE,
    Region.HOKKAIDO_SW: ClimateZone.HOKKAIDO_SW,
    Region.AOMORI: ClimateZone.TOHOKU_NORTH,
    Region.IWATE: ClimateZone.TOHOKU_NORTH,
    Region.AKITA: ClimateZone.TOHOKU_NORTH,
    Region.MIYAGI: ClimateZone.TOHOKU_SOUTH,
    Region.YAMAGATA: ClimateZone.TOHOKU_SOUTH,
    Region.FUKUSHIMA: ClimateZone.TOHOKU_SOUTH,
    Region.NIIGATA: ClimateZone.TOHOKU_SOUTH,
    Region.NAGANO: ClimateZone.TOHOKU_SOUTH,
    Region.TOYAMA: ClimateZone.HOKURIKU,
    Region.ISHIKAWA: ClimateZone.HOKURIKU,
    Region.FUKUI: ClimateZone.HOKURIKU,
    Region.OKINAWA: ClimateZone.OKINAWA,
}

# 気候区分ごとの旬のずれ（東京基準。正の値は遅く、負の値は早く）
_ZONE_OFFSETS: dict[ClimateZone, dict[ViewingShift, int]] = {
    ClimateZone.HOKKAIDO_NE: {
        ViewingShift.SPRING: 5,
        ViewingShift.AUTUMN: -4,
        ViewingShift.WINTER: 11,
    },
    ClimateZone.HOKKAIDO_SW: {
        ViewingShift.SPRING: 4,
        ViewingShift.AUTUMN: -3,
        ViewingShift.WINTER: 10,
    },
    ClimateZone.TOHOKU_NORTH: {
        ViewingShift.SPRING: 3,
        ViewingShift.AUTUMN: -2,
        ViewingShift.WINTER: 8,
    },
    ClimateZone.TOHOKU_SOUTH: {
        ViewingShift.SPRING: 2,
        ViewingShift.AUTUMN: -1,
        ViewingShift.WINTER: 5,
    },
    ClimateZone.HOKURIKU: {
        ViewingShift.SPRING: 1,
        ViewingShift.AUTUMN: 0,
        ViewingShift.WINTER: 3,
    },
    ClimateZone.STANDARD: {
        ViewingShift.SPRING: 0,
        ViewingShift.AUTUMN: 0,
        ViewingShift.WINTER: 0,
    },
}


def zone_for_region(region: str | None) -> ClimateZone:
    """地域から気候区分を返す。未設定・不明な値は基準（関東〜九州の平野部）。"""
    return _REGION_ZONES.get(region or "", ClimateZone.STANDARD)


def is_viewing_supported(zone: ClimateZone) -> bool:
    """本州基準のずらしで見ごろを表せる区分かどうか（沖縄は対象外）。"""
    return zone in _ZONE_OFFSETS


def viewing_offset(zone: ClimateZone, shift: str, adjust: int = 0) -> int:
    """気候区分と微調整から、見ごろを何旬ずらすかを返す。

    :param adjust: ``ClimateAdjust`` の値。寒い場所（+1）は春・冬の花を遅く、
        紅葉・実を早くする。
    """
    try:
        shift_type = ViewingShift(shift)
    except ValueError:
        shift_type = ViewingShift.NONE
    if shift_type == ViewingShift.NONE:
        return 0
    base = _ZONE_OFFSETS.get(zone, {}).get(shift_type, 0)
    if shift_type == ViewingShift.AUTUMN:
        return base - adjust
    return base + adjust
