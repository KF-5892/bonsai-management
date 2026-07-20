"""bonsai アプリのビュー最小スモークテスト。"""

from __future__ import annotations

from django.urls import reverse

from apps.bonsai.models import BonsaiPlant


def test_home_redirects_when_anonymous(client):
    """ホームへの未ログインアクセスはログイン画面へリダイレクトされる。"""
    res = client.get(reverse("bonsai:home"))
    assert res.status_code == 302


def test_home_renders_with_todos(client, user, bonsai_species):
    """ログインしてホームにアクセスすると 200 で ToDo が描画される。"""
    BonsaiPlant.objects.create(user=user, species=bonsai_species, name="一郎")
    client.force_login(user)
    res = client.get(reverse("bonsai:home"))
    assert res.status_code == 200
    # コンテキストに todos が入っている
    assert "todos" in res.context
    assert "plants" in res.context


def test_home_renders_empty_state(client, user):
    """盆栽未登録時は空状態（登録導線）が描画される。"""
    client.force_login(user)
    res = client.get(reverse("bonsai:home"))
    assert res.status_code == 200
    assert res.context["has_plants"] is False
    assert "まだ盆栽が登録されていません" in res.content.decode()


def test_home_filters_by_query_and_status(client, user, bonsai_species):
    """?q=（名前部分一致）と ?status=（健康状態）でマイ盆栽が絞り込まれる。"""
    BonsaiPlant.objects.create(
        user=user, species=bonsai_species, name="黒松 太郎", health_status="good"
    )
    BonsaiPlant.objects.create(
        user=user, species=bonsai_species, name="真柏 雲海", health_status="watch"
    )
    client.force_login(user)

    res = client.get(reverse("bonsai:home"), {"q": "黒松"})
    assert [p.name for p in res.context["plants"]] == ["黒松 太郎"]

    res = client.get(reverse("bonsai:home"), {"status": "watch"})
    assert [p.name for p in res.context["plants"]] == ["真柏 雲海"]
    # 絞り込みで 0 件でも所持していれば空状態にはならない
    assert res.context["has_plants"] is True


def test_other_user_cannot_view_my_bonsai(client, user, other_user, bonsai_species):
    """他ユーザーの盆栽詳細にアクセスすると 404 を返す。"""
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="自分の")
    client.force_login(other_user)
    res = client.get(reverse("bonsai:detail", kwargs={"pk": plant.pk}))
    assert res.status_code == 404


def test_species_detail_is_public(client, bonsai_species):
    """品種詳細はログイン不要で 200 を返す。"""
    res = client.get(reverse("bonsai:species_detail", kwargs={"slug": bonsai_species.slug}))
    assert res.status_code == 200
