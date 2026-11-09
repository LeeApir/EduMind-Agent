import pytest

from scripts.diagnose_head_course_t115 import diagnostic_stem

PREFIX = "请推导返回值。\n\n"
SOURCE = "#include <stdlib.h>\nint main(void) {\n    return 0;\n}\n"


@pytest.mark.parametrize("observed", [SOURCE, SOURCE[:-1]])
def test_exact_scenario_or_single_missing_lf(observed):
    assert diagnostic_stem(PREFIX + observed, SOURCE) == PREFIX + SOURCE


@pytest.mark.parametrize(
    "observed",
    [
        SOURCE[:-2],
        SOURCE.replace("    return", "  return"),
        SOURCE.replace("\n", "\r\n"),
        SOURCE[:-1] + " ",
        SOURCE + "\n",
        SOURCE.replace("return 0", "return 1"),
        "#include <stdlib.h>\n" + SOURCE,
    ],
)
def test_other_scenario_differences_are_rejected(observed):
    with pytest.raises(ValueError, match="beyond the terminal LF"):
        diagnostic_stem(PREFIX + observed, SOURCE)
