"""Strict ID selection. Model prose has no path to a result."""
import json

def validate_selection(raw: str, candidate_ids: tuple[str, ...], bullet_count: int) -> tuple[str, ...]:
    def object_pairs(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('SUMMARY_OUTPUT_INVALID')
            result[key]=value
        return result
    try:
        if type(raw) is not str or len(raw.encode('utf-8'))>8192 or type(bullet_count) is not int or bullet_count not in (3,5):raise ValueError()
        if type(candidate_ids) is not tuple or len(candidate_ids)>128 or len(set(candidate_ids))!=len(candidate_ids) or any(type(x) is not str for x in candidate_ids):raise ValueError()
        data=json.loads(raw,object_pairs_hook=object_pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(data) is not dict or set(data)!={'selected_ids'}:raise ValueError()
        ids=data['selected_ids']
        if type(ids) is not list or len(ids)>bullet_count or any(type(x) is not str or x not in candidate_ids for x in ids) or len(set(ids))!=len(ids):raise ValueError()
        return tuple(x for x in candidate_ids if x in ids)
    except (ValueError,TypeError,UnicodeError,RecursionError):raise ValueError('SUMMARY_OUTPUT_INVALID') from None
