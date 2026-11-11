from converter.errors_map.mapping import (
    MAPPING_TABLE,
    OTHER_VARIANT,
    variant_name_for_python_exception,
)


def test_exact_python_exception_maps_to_same_variant():
    assert variant_name_for_python_exception("ValueError") == "ValueError"
    assert variant_name_for_python_exception("ZeroDivisionError") == "ZeroDivisionError"


def test_mro_fallback_maps_subclass_to_base_variant():
    mro = ["UnicodeDecodeError", "UnicodeError", "ValueError", "Exception", "BaseException"]
    assert variant_name_for_python_exception("UnicodeDecodeError", mro) == "ValueError"


def test_unknown_exception_maps_to_other():
    assert variant_name_for_python_exception("CustomError") == OTHER_VARIANT


def test_exact_name_wins_before_mro():
    mro = ["KeyError", "LookupError", "Exception"]
    assert variant_name_for_python_exception("KeyError", mro) == "KeyError"


def test_mapping_table_names_match_variants():
    for python_name, variant in MAPPING_TABLE.items():
        assert python_name == variant
