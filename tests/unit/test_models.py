# tests/unit/test_models.py
import pytest
from app.core.models import Item


def test_item_normalization():
    it = Item(name="  Tomatoes  ", quantity=2, unit="Grams")
    assert it.normalized_name() == "tomatoes"
    assert it.normalized_unit() == "g"


def test_item_key_includes_unit():
    a = Item(name="Milk", quantity=1, unit="ml")
    b = Item(name="Milk", quantity=1, unit="l")
    assert a.key() != b.key()


def test_item_name_cannot_be_blank():
    with pytest.raises(Exception):
        Item(name="  ", quantity=1)
