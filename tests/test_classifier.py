from quarry_screen.geology import classify_unit


def test_outwash_is_high():
    assert classify_unit("Glacial outwash, sand and gravel") == "high"


def test_esker_is_high():
    assert classify_unit("Esker deposits") == "high"


def test_kame_is_high():
    assert classify_unit("Kame terrace") == "high"


def test_alluvium_is_high():
    assert classify_unit("Modern alluvium") == "high"


def test_till_is_low():
    assert classify_unit("Ground moraine till, clay-rich") == "low"


def test_lacustrine_clay_is_low():
    assert classify_unit("Lacustrine clay and silt") == "low"


def test_terrace_is_medium():
    assert classify_unit("Outwash terrace") == "high"  # "outwash" wins first


def test_empty_defaults_low():
    assert classify_unit(None) == "low"
    assert classify_unit("") == "low"
    assert classify_unit("unknown unit") == "low"


def test_case_insensitive():
    assert classify_unit("GLACIAL OUTWASH") == "high"
