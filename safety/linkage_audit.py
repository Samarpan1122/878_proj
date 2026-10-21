"""Bounded, nonpersistent matching and independent-review arithmetic."""
import math
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Review(Strict):
    case_id: str = Field(min_length=1, max_length=100)
    proposed_segment_id: str | None = Field(default=None, max_length=100)
    reviewed_segment_id: str | None = Field(default=None, max_length=100)
    decision: Literal['correct','incorrect','unresolved']
    notes: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def consistent(self):
        if self.decision != 'unresolved':
            if not self.proposed_segment_id or not self.reviewed_segment_id:
                raise ValueError('Resolved review requires proposed and independently reviewed road IDs')
            if (self.proposed_segment_id == self.reviewed_segment_id) != (self.decision == 'correct'):
                raise ValueError('Review decision contradicts the proposed and reviewed road IDs')
        return self


class Reviews(Strict):
    reviews: list[Review] = Field(min_length=1, max_length=100)


class PointCase(Strict):
    case_id: str = Field(min_length=1, max_length=100)
    lat: float = Field(ge=39, le=44)
    lng: float = Field(ge=-105, le=-94)


class Points(Strict):
    records: list[PointCase] = Field(min_length=1, max_length=50)


def summarize_reviews(request, snapshot):
    rows = request.reviews
    if len({r.case_id for r in rows}) != len(rows):
        raise ValueError('Duplicate case IDs would bias the audit')
    correct = sum(r.decision == 'correct' for r in rows)
    incorrect = sum(r.decision == 'incorrect' for r in rows)
    resolved = correct + incorrect
    interval, precision = None, None
    if resolved:
        precision = correct / resolved
        z = 1.959963984540054
        denominator = 1 + z*z/resolved
        midpoint = (precision + z*z/(2*resolved))/denominator
        half = z * math.sqrt(precision*(1-precision)/resolved+z*z/(4*resolved*resolved))/denominator
        interval = [max(0.,midpoint-half),min(1.,midpoint+half)]
    return {'review_count':len(rows),'resolved_count':resolved,'correct':correct,'incorrect':incorrect,
            'unresolved':len(rows)-resolved,'precision_among_resolved':precision,
            'precision_wilson95':interval,'unresolved_fraction':(len(rows)-resolved)/len(rows),
            'reviews':[r.model_dump() for r in rows], 'snapshot_built_at':snapshot['built_at'],
            'interpretation':'Agreement with user-supplied independent road labels among resolved reviewed cases.',
            'limitations':['User-supplied reviews are not verified by the application or saved to a server.',
                           'Convenience sampling, label errors and clustered cases can bias the result; Wilson interval assumes independent binomial cases.',
                           'This audit does not establish overall network accuracy or validate a safety effect.']}


def register_linkage_routes(app, required_snapshot, root):
    @app.get('/api/safety/linkage/summary')
    def summary():
        snapshot = required_snapshot()
        return {'quality':snapshot.get('quality',{}),'snapshot_built_at':snapshot['built_at'],
                'provenance':snapshot.get('provenance',{}),
                'interpretation':'Historical crash-to-road linkage coverage; match rate is not matching accuracy.',
                'limitations':snapshot.get('limitations',[])}

    @app.post('/api/safety/linkage/review')
    def review(request: Reviews):
        try:
            return summarize_reviews(request, required_snapshot())
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc

    @app.post('/api/safety/linkage/match')
    def match(request: Points):
        from safety.road_geometry import match_points
        if len({r.case_id for r in request.records}) != len(request.records):
            raise HTTPException(422,'Case IDs must be unique')
        try:
            return match_points([r.model_dump() for r in request.records],required_snapshot(),root)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            raise HTTPException(503,'Verified road geometry is unavailable for this release') from exc
