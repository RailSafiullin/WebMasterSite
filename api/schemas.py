from uuid import UUID
from enum import Enum
from typing import Optional

from pydantic import BaseModel, model_validator

from api.config.models import AutoUpdatesMode


class AutoUpdatesScheduleBase(BaseModel):
    mode: AutoUpdatesMode
    days: Optional[list[int]] = None
    hours: Optional[int] = None
    minutes: Optional[int] = None


class AutoUpdatesScheduleRead(AutoUpdatesScheduleBase):
    id: UUID


class AutoUpdatesScheduleCreate(AutoUpdatesScheduleBase):
    @staticmethod
    def _are_days_in_range(days, max_range):
        if len(days) > max_range:
            return False
        for day in days:
            if day < 1 or day > max_range:
                return False
        return True

    @model_validator(mode="after")
    def validator(self):
        if self.mode == AutoUpdatesMode.Disabled:
            return self 
        if self.days is None or len(self.days) == 0:
            raise ValueError("days not specified")
        if self.hours is None:
            raise ValueError("hours not specified")
        if self.hours < 0 or self.hours >= 24:
            raise ValueError("invalid hours range")
        if self.minutes is None:
            raise ValueError("hours not specified")
        if self.minutes < 0 or self.hours >= 60:
            raise ValueError("invalid minutes range") 
        if (self.mode == AutoUpdatesMode.WeekDays and 
            not self._are_days_in_range(self.days, 7)):
            raise ValueError("week days out of range")
        if (self.mode == AutoUpdatesMode.MonthDays and 
            not self._are_days_in_range(self.days, 31)):
            raise ValueError("month days out of range") 
        return self
