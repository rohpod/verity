from verity_core.graph.dynamodb.capacity import (
    READ_UNIT_BYTES,
    WRITE_UNIT_BYTES,
    item_size,
    read_units,
    write_units,
)


def test_a_string_attribute_is_its_name_plus_its_utf8_bytes():
    assert item_size({"a": {"S": "abc"}}) == 1 + 3
    assert item_size({"name": {"S": "é"}}) == 4 + 2  # "é" is two bytes in UTF-8


def test_a_number_is_about_one_byte_per_two_digits_plus_one():
    assert item_size({"n": {"N": "1"}}) == 1 + 2
    assert item_size({"n": {"N": "123"}}) == 1 + 3  # 3 digits -> 2 bytes + 1
    assert item_size({"n": {"N": "1000"}}) == 1 + 2  # trailing zeros are trimmed: 1 digit
    assert item_size({"n": {"N": "-0.25"}}) == 1 + 2  # sign and point are free: digits 2 and 5


def test_an_item_is_the_sum_of_its_attributes():
    item = {"PK": {"S": "xx"}, "ver": {"N": "7"}}
    assert item_size(item) == (2 + 2) + (3 + 2)


def test_a_write_unit_is_one_kilobyte_rounded_up_and_transactions_cost_double():
    assert write_units(1) == 1 and write_units(WRITE_UNIT_BYTES) == 1
    assert write_units(WRITE_UNIT_BYTES + 1) == 2
    assert write_units(500, transactional=True) == 2
    assert write_units(1500, transactional=True) == 4
    assert write_units(0) == 1


def test_a_read_adds_items_before_rounding_to_four_kilobytes():
    assert read_units([1000] * 5) == 2  # 5000 bytes -> 2 units, not 5
    assert read_units([READ_UNIT_BYTES]) == 1
    assert read_units([READ_UNIT_BYTES + 1]) == 2
    assert read_units([1000] * 5, consistent=False) == 1.0  # eventually consistent is half
