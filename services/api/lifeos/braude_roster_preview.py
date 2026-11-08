"""Unwired, read-only roster comparison for the approved synthetic-source proof."""

import io
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
)
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .academic_models import Course, Term
from .account_records import AccountRecords
from .braude_academic import read_roster, source_state


class RosterSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    account_id: str
    observed_at: AwareDatetime
    year: StrictInt
    semester: StrictInt
    start_date: date | None = None
    end_date: date | None = None
    complete: StrictBool

    @field_validator('start_date', 'end_date', mode='before')
    @classmethod
    def explicit_date(cls, value):
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value)):
            raise ValueError('Explicit date-only source value required')
        return value


class BraudeRosterPreview(AccountRecords):
    def compare(self, owner, export_bytes, metadata):
        result = dict(fixture=True, status='needs_review', reason=None, observed_at=None,
                      rows=[], counts=dict(unchanged=0, added=0, changed=0, missing=0))

        def stop(reason):
            return result | {'reason': reason}

        with Session(self.engine) as db:
            db.execute(text('BEGIN'))
            self.authorize(db, owner)
            try:
                source = RosterSource.model_validate(metadata)
            except (ValidationError, TypeError):
                return stop('invalid_source')
            if source.account_id != owner:
                raise PermissionError('Source account mismatch')
            result['observed_at'] = source.observed_at.astimezone(timezone.utc).isoformat()
            if not source.complete:
                return stop('incomplete_source')
            if source.observed_at > datetime.now(timezone.utc) + timedelta(minutes=5) or not 2000 <= source.year <= 2100:
                return stop('invalid_source')
            if source.semester != 1:
                return stop('unsupported_semester')
            if source.start_date is None or source.end_date is None:
                return stop('missing_term_dates')
            term_id = str(uuid5(NAMESPACE_URL, f'{owner}/braude/{source.year}/{source.semester}'))
            term = db.get(Term, term_id)
            if term is None or term.account_id != owner:
                return stop('unknown_term')
            if (term.start_date != source.start_date.isoformat() or term.end_date != source.end_date.isoformat()
                    or source.start_date > source.end_date):
                return stop('term_mismatch')
            if not isinstance(export_bytes, bytes) or not 0 < len(export_bytes) <= 4 * 1024 * 1024:
                return stop('invalid_export')
            try:
                roster = read_roster(io.BytesIO(export_bytes))
            except Exception:
                return stop('invalid_export')

            state = source_state(db, owner)
            local = list(db.scalars(select(Course).where(Course.term_id == term_id)))
            codes = Counter(course.code for course in local if course.code)
            if any(count > 1 for count in codes.values()):
                return stop('ambiguous_local_codes')
            by_code = {course.code: course for course in local}
            imported = {course.code: course for course in local if course.id in state.courses}
            rows = []
            for entry in roster:
                code = entry['code']
                current = imported.get(code)
                if current is None and code in by_code:
                    return stop('manual_course_conflict')
                fields = [field for field in ('name', 'instructor')
                          if current is not None and entry[field] and entry[field] != getattr(current, field)]
                kind = 'added' if current is None else 'changed' if fields else 'unchanged'
                rows.append(dict(kind=kind, code=code, name=entry['name'],
                                 local_name=current.name if current else None,
                                 source_name=entry['name'],
                                 local_instructor=current.instructor if current else None,
                                 source_instructor=entry['instructor'] or None, fields=fields,
                                 missing_fields=['instructor'] if not entry['instructor'] else []))
            seen = {entry['code'] for entry in roster}
            rows.extend(dict(kind='missing', code=course.code, name=course.name,
                             local_name=course.name, source_name=None,
                             local_instructor=course.instructor, source_instructor=None,
                             fields=[], missing_fields=[]) for code, course in imported.items() if code not in seen)
            result.update(status='ready', reason=None, rows=sorted(rows, key=lambda row: row['code']),
                          counts={kind: sum(row['kind'] == kind for row in rows) for kind in result['counts']})
            return result
