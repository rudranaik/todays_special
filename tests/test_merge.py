# tests/unit/test_merge.py
from app.core.merge import apply_merge
from app.core.models import Item, Pantry


def test_merge_adds_quantities_for_same_key():
    pantry = Pantry(items=[Item(name="Tomato", quantity=2, unit="g")])
    incoming = [Item(name="tomato", quantity=3, unit="grams")]
    out = apply_merge(pantry, incoming)
    assert len(out.items) == 1
    assert out.items[0].quantity == 5
    assert out.items[0].normalized_unit() == "g"


def test_merge_keeps_distinct_units_separate():
    pantry = Pantry(items=[Item(name="Milk", quantity=500, unit="ml")])
    incoming = [Item(name="milk", quantity=1, unit="l")]
    out = apply_merge(pantry, incoming)
    assert len(out.items) == 2
    names_units = {(i.normalized_name(), i.normalized_unit()) for i in out.items}
    assert ("milk", "ml") in names_units
    assert ("milk", "l") in names_units


def test_merge_inserts_new_items_when_absent():
    pantry = Pantry(items=[])
    incoming = [Item(name="Onion", quantity=2, unit="piece")]
    out = apply_merge(pantry, incoming)
    assert len(out.items) == 1
    assert out.items[0].name == "Onion"
    assert out.items[0].quantity == 2


def test_merge_is_deterministically_sorted():
    pantry = Pantry(items=[])
    incoming = [
        Item(name="Bananas", quantity=1, unit="piece"),
        Item(name="apple", quantity=1, unit="piece"),
        Item(name="Carrot", quantity=1, unit="g"),
    ]
    out = apply_merge(pantry, incoming)
    assert [i.normalized_name() for i in out.items] == ["apple", "bananas", "carrot"]
