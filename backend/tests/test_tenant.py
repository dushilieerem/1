# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from services.core.tenant import OrgScope, Tenant


def test_tenant_validation_and_params():
    t = Tenant.from_pair(7, 3)
    assert t.params() == (7, 3)
    for uid, org in ((0, 3), (7, 0), (True, 3), (7, "3")):
        with pytest.raises(ValueError):
            Tenant(uid, org)


def test_tenant_from_ctx():
    assert Tenant.from_ctx({"user": {"id": 7}, "org": {"id": 3}}) == Tenant(7, 3)
    assert Tenant.from_ctx({"user_id": 8, "org": {"id": 4}}) == Tenant(8, 4)
    with pytest.raises(ValueError):
        Tenant.from_ctx({"user": {"id": 7}})

def test_org_scope_validation():
    assert OrgScope(3).org_id == 3
    for value in (0, True, "3"):
        with pytest.raises(ValueError):
            OrgScope(value)
