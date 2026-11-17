"""Compatibility imports for the historical T119 stack trial."""

from app.services.course_trial_publication import (
    STACK,
)
from app.services.course_trial_publication import (
    assembly as assembly,
)
from app.services.course_trial_publication import (
    candidate as candidate,
)
from app.services.course_trial_publication import (
    context as context,
)
from app.services.course_trial_publication import (
    fingerprint as fingerprint,
)
from app.services.course_trial_publication import (
    prepare as prepare,
)
from app.services.course_trial_publication import (
    publish as publish,
)
from app.services.course_trial_publication import (
    require_database as require_database,
)
from app.services.course_trial_publication import (
    validate_publication as validate_publication,
)

DATABASE = STACK.database
TEST_DATABASE = DATABASE + "_test"
CHECKS = STACK.checks
