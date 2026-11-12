import './domSetup.mjs';
import React from 'react';
import test,{afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {render,cleanup,fireEvent} from '@testing-library/react';
import {FactorNoveltyEvidence} from '../src/pages/institutional-workflow/FactorNoveltyEvidence';
import {FactorNoveltyPlan} from '../src/pages/institutional-workflow/FactorNoveltyPlan';
afterEach(cleanup);
test('missing comparison does not display a successful novelty gate',()=>{
 const v=render(<FactorNoveltyEvidence purpose="discovery"/>);
 assert.ok(v.getByText(/尚无数值去重证据/));
 assert.equal(v.queryByText('预登记去重条件通过'),null);
});
test('replication is explicitly not a new discovery',()=>{
 const v=render(<FactorNoveltyEvidence purpose="replication"/>);
 assert.ok(v.getByText('已有因子复现：不申报新发现。'));
});
test('incomplete full-library comparison shows missing rows instead of zero correlation',()=>{
 const v=render(<FactorNoveltyEvidence evidence={{status:'incomplete',gate:{passed:false,complete:false,expected_count:334,compared_count:1,max_abs_correlation:null,threshold:.8,limitation:'scope'}}}/>);
 assert.ok(v.getByText('1 / 334'));
 assert.ok(v.getByText(/未取得完整有效/));
 assert.ok(v.getByText('未取得（上限 0.8）'));
});
test('opposite or scaled duplicate remains visible as high absolute correlation',()=>{
 const v=render(<FactorNoveltyEvidence evidence={{status:'failed',gate:{passed:false,complete:true,expected_count:1,compared_count:1,max_abs_correlation:1,threshold:.8,limitation:'scope'},comparisons:[{reference_id:'lib:old',status:'succeeded',mean_abs_spearman:1,valid_days:100,min_pairs:200,coverage:1}]}}/>);
 assert.ok(v.getByText('去重条件未通过'));
 assert.ok(v.getByText('1.0000（上限 0.8）'));
 assert.ok(v.getByText('查看逐项比较证据（1 项）'));
});
test('old plans require explicit purpose and cannot silently become new discovery',()=>{
 let changed:any;
 const v=render(<FactorNoveltyPlan plan={{} as any} onChange={p=>{changed=p;}}/>);
 assert.equal((v.getByRole('combobox') as HTMLSelectElement).value,'');
 fireEvent.change(v.getByRole('combobox'),{target:{value:'discovery'}});
 assert.equal(changed.researchPurpose,'discovery');
 assert.equal(changed.noveltyPolicy.scope,'all_accessible');
 assert.equal(changed.noveltyPolicy.maxAbsCorrelation,.8);
});
