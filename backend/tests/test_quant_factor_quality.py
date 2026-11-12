from services.quant_factor.quality import assess


def row(**overrides):
    base={'snapshot':{'request':{'start':'2025-07-01','end':'2025-09-30','commission_rate':0,'stamp_tax':0,'slippage_rate':0,'universe_snapshot':{'symbols':['000001.SZ']}}},
          'evidence':{'development':{'gate':{'k_used':5,'checks':[{'name':'有效IC观测数','actual':61}]},'result':{'metrics':{'turnover':.535,'total_cost':0}},'novelty':{'status':'deferred','gate':{'passed':False}}}}}
    for path,value in overrides.items():
        target=base
        parts=path.split('.')
        for part in parts[:-1]:target=target[part]
        target[parts[-1]]=value
    return base


def test_zero_cost_short_sample_and_pending_novelty_are_visible_but_not_gates():
    out=assess(row())
    codes={f['code'] for f in out['flags']}
    assert {'zero_cost','short_sample','short_window','high_turnover','novelty_pending','multiple_trials'} <= codes
    assert out['advisory_only'] is True
    assert out['costs']['commission_rate']==0


def test_real_costs_and_long_sample_remove_cost_and_sample_flags():
    out=assess(row(**{'snapshot.request.commission_rate':.0003,'snapshot.request.stamp_tax':.001,'snapshot.request.slippage_rate':.0005,
                      'snapshot.request.start':'2024-01-01','snapshot.request.end':'2025-12-31',
                      'evidence.development.gate.checks':[{'name':'有效IC观测数','actual':250}],
                      'evidence.development.novelty':{'status':'passed','gate':{'passed':True,'threshold':.7}},
                      'evidence.development.result.metrics.turnover':.1}))
    codes={f['code'] for f in out['flags']}
    assert 'zero_cost' not in codes
    assert 'short_sample' not in codes
    assert 'short_window' not in codes
    assert 'novelty_pending' not in codes
    assert 'high_turnover' not in codes
