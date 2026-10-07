from dataclasses import dataclass,field

@dataclass(frozen=True)
class Candidate:
    candidate_id:str
    quote:str=field(repr=False)
    evidence:dict=field(repr=False)
