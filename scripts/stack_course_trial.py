"""Compatibility entry for the historical T119 stack trial."""

import sys

from scripts.course_trial_generation import (
    PACKAGE as PACKAGE,
    VAULT as VAULT,
    approval_values as approval_values,
    legacy_main as main,
    local_gate as local_gate,
    package_digest as package_digest,
    prepare as prepare,
    publish as publish,
    raw_io as raw_io,
    read as read,
    replay as replay,
    send as send,
)

if __name__ == "__main__":
    sys.exit(main())
