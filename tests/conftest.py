# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173
"""Default-contract tests run with the served HIRAG opt-in unset, whatever the caller's shell exports."""
import pytest

from second_brain import admission_runtime


@pytest.fixture(autouse=True)
def _served_admission_default(monkeypatch):
    monkeypatch.delenv(admission_runtime.OPT_IN_ENV, raising=False)
    admission_runtime.reset_runtime_admission()
    yield
    admission_runtime.reset_runtime_admission()
