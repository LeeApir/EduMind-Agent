"""Partition guard with synthetic placeholders; no held-out semantics used for tuning."""

import sys
from pathlib import Path
from copy import deepcopy
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_holdout_reserve import check_partition  # noqa:E402


def fixture():
    return dict(
        id="new",
        original_request="unseen target",
        partition="reserved_holdout",
        not_for_prompt_tuning=True,
        generated_material=None,
        actual_model_result=None,
        reviewer_model_result=None,
    )


def test_unseen_placeholders_can_be_reserved():
    check_partition([fixture()], [dict(id="old", original_request="known target")])


@pytest.mark.parametrize("alias", ["id", "goal", "duplicate", "observation"])
def test_no_relabeling_development_or_used_data_as_holdout(alias):
    a = fixture()
    rows = [a]
    old = [dict(id="old", original_request="known target")]
    if alias == "id":
        a["id"] = "old"
    elif alias == "goal":
        a["original_request"] = "known target"
    elif alias == "duplicate":
        rows.append(deepcopy(a))
    else:
        a["actual_model_result"] = {"verdict": "pass"}
    with pytest.raises(ValueError):
        check_partition(rows, old)
