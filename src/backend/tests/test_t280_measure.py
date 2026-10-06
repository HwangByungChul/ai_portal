import pytest
from scripts.t280_measure import percentile,summarize

def test_nearest_rank_twentieth_sample_p95_is_nineteenth():
    assert percentile(list(range(20,0,-1)),.95)==19
    assert percentile([3,1,2],.5)==2

@pytest.mark.parametrize('values',[[],[float('nan')],[float('inf')],[-1]])
def test_invalid_samples_cannot_manufacture_latency(values):
    with pytest.raises(ValueError):percentile(values,.95)

def test_error_and_missing_samples_do_not_become_performance_pass():
    rows=[{'duration_ms':1,'status':200,'scope_valid':True} for _ in range(20)]
    assert summarize(rows,300)['verdict']=='pass'
    rows[-1]={'duration_ms':1,'status':404,'scope_valid':False}
    report=summarize(rows,300);assert report['verdict']=='fail' and report['errors']==1 and len(report['samples'])==20
    assert summarize(rows[:19],300)['verdict']=='fail'
