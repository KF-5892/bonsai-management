"""bonsai モデルのスモーク・最小認可テスト。"""

from __future__ import annotations

from apps.bonsai.models import BonsaiPlant, HealthStatus


def test_create_bonsai_plant(user, bonsai_species):
    plant = BonsaiPlant.objects.create(
        user=user,
        species=bonsai_species,
        name="太郎",
    )
    assert plant.id  # UUIDv7 が採番されている
    assert plant.user == user
    assert plant.species == bonsai_species
    assert plant.health_status == HealthStatus.GOOD
    assert str(plant) == "太郎"


def test_bonsai_queryset_isolated_per_user(user, other_user, bonsai_species):
    BonsaiPlant.objects.create(user=user, species=bonsai_species, name="自分の盆栽")
    BonsaiPlant.objects.create(user=other_user, species=bonsai_species, name="他人の盆栽")

    mine = BonsaiPlant.objects.filter(user=user)
    theirs = BonsaiPlant.objects.filter(user=other_user)

    assert mine.count() == 1
    assert theirs.count() == 1
    assert mine.first().name == "自分の盆栽"
    assert theirs.first().name == "他人の盆栽"

    # 他ユーザーの個体は own queryset から見えない
    assert not mine.filter(name="他人の盆栽").exists()
    # ユーザー ID も一致しないことを確認（user FK の取り違えを防ぐ）
    assert mine.first().user_id == user.id
    assert theirs.first().user_id == other_user.id
