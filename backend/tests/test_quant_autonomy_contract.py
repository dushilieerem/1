import copy
import json
import socket
import unittest
from unittest.mock import patch

from services.quant_factor.research_experience import private_development, bounded_context
from services.quant_factor.autonomy_contract import family_key, input_fingerprint, consumption, trial_permission, validate_proposal, may_apply


def scope():
    return {"org_id": 901, "authority_lineage_id": "authorization_origin", "version": 1,
            "data_identity": {"view_id": "fixed-v1", "view_manifest_sha256": "a" * 64,
                              "daily_release": "release-v1", "daily_dataset_sha256": "b" * 64},
            "universe_snapshot": ["000001.SZ", "600000.SH"], "development": ["2025-07-01", "2025-09-30"],
            "forecast_horizon_sessions": 1, "ic_metric": "rank_ic", "allowed_fields": ["close", "volume"]}


def fixtures():
    topic = {"id": "t", "project_id": "p", "user_id": 7, "org_id": 901, "view_id": "fixed-v1", "primary_holding_period": 1}
    trial = {"id": "trial-1", "project_id": "p", "topic_id": "t", "user_id": 7, "org_id": 901,
             "branch_id": "h", "kind": "agent", "report_id": "report-1"}
    gate = {"passed": False, "metric_type": "rank_ic", "k_used": 2,
            "checks": [{"name": "方向Rank IC", "actual": .04, "threshold": .02, "passed": True},
                       {"name": "最大回撤", "actual": .1, "threshold": .3, "passed": True},
                       {"name": "有效IC观测数", "actual": 60, "threshold": 60, "passed": True},
                       {"name": "方向 NW t", "actual": 1.63, "threshold": 2.24, "passed": False}]}
    candidate = {"id": "e", "project_id": "p", "user_id": 7, "org_id": 901, "snapshot_hash": "frozen",
                 "snapshot": {"rules": {"icMetric": "rank_ic"}, "request": {"factor_code": "private code"},
                              "plan": {"hypothesis": "test hypothesis", "validation": {"ic": "SECRET_HELDOUT"},
                                       "researchContract": {"data_identity": {"universe": ["000001.SZ"], "development": ["2025-07-01", "2025-09-30"]}}}},
                 "evidence": {"branch_id": "h", "development": {"report_id": "report-1", "gate": gate,
                              "result": {"factor_analysis": {"rank_ic_series": [{"value": 999}]}}},
                              "sealed": {"ic": "SECRET_HELDOUT"}, "review": {"comment": "SECRET_REVIEW"}}}
    return candidate, trial, topic


class StagingTests(unittest.TestCase):
    def test_private_access_and_source_join_reject_cross_actor_or_wrong_report(self):
        c, t, topic = fixtures()
        for actor in ((8, 901), (7, 902)):
            with self.assertRaises(PermissionError): private_development(actor, c, t, topic)
        t["report_id"] = "another-report"
        with self.assertRaises(ValueError): private_development((7, 901), c, t, topic)

    def test_only_development_whitelist_is_available_to_planner(self):
        c, t, topic = fixtures(); row = private_development((7, 901), c, t, topic)
        serialized = json.dumps(row)
        self.assertNotIn("SECRET_", serialized); self.assertNotIn("private code", serialized)
        self.assertNotIn("rank_ic_series", serialized)
        self.assertEqual(row["facts"]["category"], "unsupported_in_scope")
        self.assertTrue(row["facts"]["sealed_exposure_recorded"])
        self.assertEqual(len(bounded_context([row, row], actor=(7, 901))), 1)

    def test_missing_observations_null_values_and_technical_errors_are_not_market_rejection(self):
        c, t, topic = fixtures()
        c["evidence"]["development"]["gate"]["checks"][2]["actual"] = None
        row = private_development((7, 901), c, t, topic)
        self.assertEqual(row["facts"]["category"], "insufficient_evidence")
        self.assertIsNone(row["facts"]["checks"][2]["actual"])
        row = private_development((7, 901), c, t, topic, technical_incomplete=True)
        self.assertEqual(row["facts"]["category"], "technical_incomplete")

    def test_resource_deferred_does_not_turn_passing_numerics_into_statistical_failure(self):
        c, t, topic = fixtures()
        c["evidence"]["development"]["gate"]["checks"][-1].update(actual=3, passed=True)
        row = private_development((7, 901), c, t, topic)
        self.assertEqual(row["facts"]["category"], "promising_development")
        self.assertNotIn("approved", row["facts"])

    def test_family_ignores_renames_project_order_direction_and_authorization_version(self):
        a = scope(); b = copy.deepcopy(a)
        b.update(version=9, project_id="new-p", direction="negative", title="rename")
        b["data_identity"]["project_id"] = "new-p"; b["universe_snapshot"].reverse()
        self.assertEqual(family_key(a), family_key(b))
        b["data_identity"]["daily_release"] = "different"
        self.assertNotEqual(family_key(a), family_key(b))

    def test_family_count_counts_distinct_exposures_not_source_names(self):
        a = {"id": "trial-a", "source": "same-code", "counted": True}
        b = {"id": "trial-b", "source": "same-code", "counted": True}
        self.assertEqual(consumption([a, b, a], counts_toward_k=lambda r: r["counted"]), 2)
        with self.assertRaises(ValueError):
            consumption([a, {**a, "counted": False}], counts_toward_k=lambda r: r["counted"])

    def test_family_k_and_lineage_remaining_are_independent(self):
        self.assertEqual(trial_permission(family_k=21, lineage_used=0, task_max_trials=2)["next_new_trial_k"], 22)
        self.assertTrue(trial_permission(family_k=21, lineage_used=0, task_max_trials=2)["allowed"])
        self.assertFalse(trial_permission(family_k=21, lineage_used=2, task_max_trials=2)["allowed"])
        self.assertFalse(trial_permission(family_k=21, lineage_used=0, task_max_trials=2, overall_used=4, overall_max_trials=4)["allowed"])

    def test_refresh_same_input_is_same_fingerprint_explicit_reconsider_changes_it(self):
        args = (scope(), "price volume", "catalogue-sha", [])
        self.assertEqual(input_fingerprint(*args), input_fingerprint(*args))
        self.assertNotEqual(input_fingerprint(*args), input_fingerprint(*args, reconsider_id="manual-click-1"))

    def test_pause_or_revocation_invalidates_late_application(self):
        p = {"authorization_id": "a", "authorization_version": 2}
        a = {"id": "a", "version": 2, "enabled": True, "member_active": True, "research_permission": True}
        self.assertTrue(may_apply(p, a))
        for changed in ({"enabled": False}, {"version": 3}, {"member_active": False}, {"research_permission": False}):
            self.assertFalse(may_apply(p, {**a, **changed}))

    def test_proposal_cannot_expand_fields_claim_evidence_or_return_authority(self):
        proposal = dict(action="proposal", title="test", hypothesis="test", mechanism="test", expected_effect="test", falsification="test",
                        required_fields=["close"], forecast_horizon_sessions=1, why_now="test", difference_from_existing="test",
                        evidence_refs=["dev_a"], related_research_refs=[], wait_reason="", change_conditions="")
        args = dict(scope=scope(), evidence_refs=["dev_a"], related_research_refs=[])
        self.assertEqual(validate_proposal(proposal, **args), proposal)
        for changed in ({"required_fields": ["turnover"]}, {"evidence_refs": ["private-other"]}, {"family_k": 0}, {"mechanism": ""}, {"forecast_horizon_sessions": True}):
            with self.assertRaises(ValueError): validate_proposal({**proposal, **changed}, **args)
        wait = {**proposal, "action": "wait", "wait_reason": "same evidence", "change_conditions": "new development evidence"}
        self.assertEqual(validate_proposal(wait, **args)["action"], "wait")


if __name__ == "__main__":
    # No database imports; block all network even if a future import regresses.
    with patch.object(socket.socket, "connect", side_effect=AssertionError("network prohibited")), patch.object(socket, "create_connection", side_effect=AssertionError("network prohibited")):
        unittest.main(verbosity=2)


import copy,unittest,uuid,socket
from unittest.mock import patch
from services.quant_factor.autonomy_authorization import prepare,original_receipt,control,may_plan,AuthorizationConflict

def member():return {'user_id':7,'org_id':901,'role':'quant_researcher','status':'active','quant_permission':'write'}
def authoritative_scope():return {**scope(),'validation':['2026-06-22','2026-09-21'],'rules':{'icMetric':'rank_ic','minObservations':60},'resource_limits':{'research_concurrency':1,'max_scoring_days':93},'task_max_trials':2,'overall_max_trials':None}

class AuthorizationTests(unittest.TestCase):
 def test_effective_scope_snapshot_and_per_task_overall_limits_are_separate(self):
  s=authoritative_scope();r=prepare((7,901),member(),s,'研究方向',str(uuid.uuid4()));s['allowed_fields'].append('turnover')
  self.assertNotIn('turnover',r['scope']['allowed_fields']);self.assertEqual(r['scope']['task_max_trials'],2);self.assertIsNone(r['scope']['overall_max_trials']);self.assertTrue(may_plan(r,(7,901),member(),1))
 def test_same_create_identity_returns_original_or_conflicts_without_overwrite(self):
  key=str(uuid.uuid4());r=prepare((7,901),member(),authoritative_scope(),'原方向',key)
  self.assertEqual(original_receipt(r,prepare((7,901),member(),authoritative_scope(),'原方向',key),(7,901)),r)
  with self.assertRaises(AuthorizationConflict):original_receipt(r,prepare((7,901),member(),authoritative_scope(),'新方向',key),(7,901))
  with self.assertRaises(PermissionError):original_receipt(r,r,(8,901))
 def test_reviewers_revoked_members_and_foreign_scope_cannot_enable(self):
  for changes in ({'role':'quant_reviewer'},{'status':'disabled'},{'quant_permission':'review'},{'org_id':902}):
   with self.subTest(changes=changes),self.assertRaises(PermissionError):prepare((7,901),{**member(),**changes},authoritative_scope(),'',str(uuid.uuid4()))
  s=authoritative_scope();s['org_id']=902
  with self.assertRaises(PermissionError):prepare((7,901),member(),s,'',str(uuid.uuid4()))
 def test_pause_retries_are_idempotent_but_new_output_needs_matching_authorization_epoch(self):
  r=prepare((7,901),member(),authoritative_scope(),'',str(uuid.uuid4()));key=str(uuid.uuid4());paused=control(r,(7,901),member(),enabled=False,expected_version=1,request_key=key)
  self.assertFalse(may_plan(paused,(7,901),member(),1));self.assertFalse(may_plan(paused,(7,901),member(),2));self.assertEqual(control(paused,(7,901),member(),enabled=False,expected_version=1,request_key=key),paused)
  with self.assertRaises(AuthorizationConflict):control(paused,(7,901),member(),enabled=True,expected_version=1,request_key=key)
  with self.assertRaises(AuthorizationConflict):control(paused,(7,901),member(),enabled=True,expected_version=1,request_key=str(uuid.uuid4()))
  resumed=control(paused,(7,901),member(),enabled=True,expected_version=2,request_key=str(uuid.uuid4()));self.assertFalse(may_plan(resumed,(7,901),member(),1));self.assertTrue(may_plan(resumed,(7,901),member(),3));self.assertEqual(resumed['family_id'],r['family_id'])
 def test_no_token_budget_is_invented_as_range_authority(self):
  s=authoritative_scope();s['token_limit']=100000000
  with self.assertRaisesRegex(ValueError,'scope is incomplete'):prepare((7,901),member(),s,'',str(uuid.uuid4()))
  s=authoritative_scope();s['task_max_trials']=True
  with self.assertRaises(ValueError):prepare((7,901),member(),s,'',str(uuid.uuid4()))

if __name__=='__main__':
 with patch.object(socket.socket,'connect',side_effect=AssertionError('isolated: no network')):unittest.main(verbosity=2)
