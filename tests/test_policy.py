import json
import pathlib

import pytest

from server.policy.engine import evaluate, validate_allocations

ROOT = pathlib.Path(__file__).resolve().parents[1]
HH = json.loads((ROOT / "data/households/family.json").read_text())
CAT = json.loads((ROOT / "data/catalog/catalog.json").read_text())


def ev(**kw):
    base = dict(spent={}, claimed=set(), pot_unlocked=True)
    base.update(kw)
    return evaluate(HH, CAT, **base)


def test_happy_path_adult():
    d = ev(buyer_id="mom", recipient="bill", sku="KF-502")
    assert d.allowed and not d.needs_approval, d.reason


def test_teen_cannot_buy_mature_game_even_for_adult():
    d = ev(buyer_id="bill", recipient="sam", sku="BB-102")
    assert not d.allowed
    assert any(c.name == "buyer_age" and not c.ok for c in d.checks)


def test_adult_cannot_buy_mature_game_for_teen():
    d = ev(buyer_id="dad", recipient="bill", sku="BB-102")
    assert not d.allowed
    assert any(c.name == "recipient_age" and not c.ok for c in d.checks)


def test_over_budget():
    d = ev(buyer_id="jill", recipient="mom", sku="CC-601", spent={"jill": 300})
    assert not d.allowed and "exceeds" in d.reason


def test_off_list_recipient():
    d = ev(buyer_id="sam", recipient="Jordan", sku="TL-402")
    assert not d.allowed and "approved friend" in d.reason


def test_approved_friend_ok():
    assert ev(buyer_id="sam", recipient="Maya", sku="TL-402").allowed


def test_duplicate_blocked():
    d = ev(buyer_id="dad", recipient="bill", sku="KF-502", claimed={("bill", "KF-502")})
    assert not d.allowed


def test_minor_needs_approval():
    d = ev(buyer_id="lucy", recipient="mom", sku="TL-402")
    assert d.allowed and d.needs_approval


def test_locked_pot():
    assert not ev(buyer_id="mom", recipient="bill", sku="KF-502", pot_unlocked=False).allowed


def test_out_of_stock():
    assert not ev(buyer_id="dad", recipient="sam", sku="BB-106").allowed


def test_log_mode_lets_failures_through_but_records_them():
    d = ev(buyer_id="bill", recipient="sam", sku="BB-102", mode="log")
    assert d.allowed and d.failed


@pytest.mark.parametrize("alloc,ok", [({"lucy": 100}, True), ({"lucy": 2000}, False), ({"mom": 5000}, False)])
def test_allocations(alloc, ok):
    assert (validate_allocations(HH, alloc) == []) is ok
