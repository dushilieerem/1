from services.quant_factor.source_compat import capability_catalog, unsupported_proposal_reason


def test_catalog_is_the_platform_surface_and_allows_np_log_but_not_bare_ln():
    cap=capability_catalog()
    assert 'np.log' in ' '.join(cap['notes'])
    assert 'log' in cap['numpy'] and 'log1p' in cap['numpy']
    assert 'close' in cap['fields']
    assert unsupported_proposal_reason('用 np.log(close) 计算') == ''
    assert (sus := unsupported_proposal_reason('用 ln(close) 计算'))
    assert '不支持的表达式能力' in sus
    assert unsupported_proposal_reason('用 math.log(close) 计算') != ''
    assert unsupported_proposal_reason('用 OLS 取残差') != ''
