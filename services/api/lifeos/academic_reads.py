"""Cooperatively bounded normal academic reads; never return truncated successes."""

import time

from fastapi import HTTPException
from sqlalchemy import select

from .academic_calendar import iter_calendar

MAX_RECORDS = 10000
MAX_STEPS = 100000
MAX_SECONDS = 10


class ReadBudget:
    def __init__(self):
        self.deadline = time.monotonic() + MAX_SECONDS
        self.steps = 0
        self.check()

    def check(self):
        self.steps += 1
        if self.steps > MAX_STEPS or time.monotonic() >= self.deadline:
            raise HTTPException(503, "academic_resource_limit")

    def collect(self, rows):
        result = []
        for row in rows:
            self.check()
            if len(result) >= MAX_RECORDS:
                raise HTTPException(503, "academic_resource_limit")
            result.append(row)
        self.check()
        return result


def read_list(db, model):
    budget = ReadBudget()
    return budget.collect(db.scalars(select(model).limit(MAX_RECORDS + 1)).yield_per(200))


def read_calendar(db):
    budget = ReadBudget()
    result = sorted(
        budget.collect(iter_calendar(db, budget.check)), key=lambda event: event["start"]
    )
    budget.check()
    return result
