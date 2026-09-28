from dataclasses import dataclass
from uuid import UUID, uuid5

from fastapi import Depends

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str
    display_name: str


class CurrentUserProvider:
    def get_user(self) -> CurrentUser:
        raise NotImplementedError


class DevelopmentCurrentUserProvider(CurrentUserProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_user(self) -> CurrentUser:
        user_id = uuid5(UUID("ef339a0c-0747-448b-aecc-8c46f57f90f7"), self.settings.dev_user_email)
        return CurrentUser(user_id, self.settings.dev_user_email, self.settings.dev_user_name)


def get_current_user(settings: Settings = Depends(get_settings)) -> CurrentUser:
    return DevelopmentCurrentUserProvider(settings).get_user()
