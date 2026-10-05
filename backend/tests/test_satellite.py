from app.satellite import boa_offset


def test_boa_offset_only_from_baseline_04():
    assert boa_offset("02.09") == 0 and boa_offset("03.01") == 0
    assert boa_offset("04.00") == 1000 and boa_offset("05.11") == 1000
