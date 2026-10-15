from call_handler import strip_stage_directions


def test_stage_directions_are_removed():
    assert strip_stage_directions("*coughs* Hello? *clears throat* Who is it?") == "Hello? Who is it?"


def test_half_streamed_stage_direction_is_removed():
    assert strip_stage_directions("Hello? *cou") == "Hello?"


def test_plain_text_is_only_whitespace_normalised():
    assert strip_stage_directions("  Haan   ji,\nboliye ") == "Haan ji, boliye"
