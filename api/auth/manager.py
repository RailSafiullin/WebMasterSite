from datetime import datetime
from email_validator import validate_email
from email_validator.exceptions_types import EmailSyntaxError, EmailNotValidError
from typing import Optional, Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from .exceptions import InvalidEmail

from fastapi import Depends
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import BaseUserManager, IntegerIDMixin, exceptions
from requests import Response

from api.auth.models import User
from api.auth.schemas import UserCreate, UserCreateWithRole
from api.auth.utils import get_user_db
from api.config.models import UserQueryCount
from config import SECRET

from fastapi import Request

from db.session import async_session_general

from const import query_value, date_format


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    reset_password_token_secret = SECRET

    verification_token_secret = SECRET

    async def get(self, user_id: int) -> Optional[User]:
        """
        Get a user by id.

        :param id: Id. of the user to retrieve.
        :raises UserNotExists: The user does not exist.
        :return: A user.
        """
        async with async_session_general() as session:
            result = await session.execute(
                select(User).options(selectinload(User.role_info)).filter(User.id == user_id)
            )
            user = result.scalars().first()

        if user is None:
            raise exceptions.UserNotExists()

        return user

    async def batch_create(self, users_create: Iterable[UserCreateWithRole], safe: bool = False):
        """
        Create users in db.
        :raises InvalidEmail
        :raises IntegrityError: when user with the same data already exists
        """
        users_dicts = []
        for user_create in users_create:
            try:
                user_create.email = validate_email(user_create.email).email 
                user_dict = (
                    user_create.create_update_dict()
                    if safe
                    else user_create.create_update_dict_superuser()
                )
                password = user_dict.pop("password")
                user_dict["hashed_password"] = self.password_helper.hash(password)
                user_dict["role"] = user_create.role
                users_dicts.append(user_dict)
            except (EmailSyntaxError, EmailNotValidError):
                raise InvalidEmail(invalid_email=user_create.email)

        async with async_session_general() as session:
            try:
                await session.run_sync(lambda session: session.bulk_insert_mappings(User, users_dicts))
                await session.commit() 
            except IntegrityError as e:
                await session.rollback()
                raise e

    async def create(
            self,
            user_create: UserCreate,
            safe: bool = False,
            request: Optional[Request] = None,
    ):
        """
        Create a user in database.

        Triggers the on_after_register handler on success.

        :param user_create: The UserCreate model to create.
        :param safe: If True, sensitive values like is_superuser or is_verified
        will be ignored during the creation, defaults to False.
        :param request: Optional FastAPI request that
        triggered the operation, defaults to None.
        :raises UserAlreadyExists: A user already exists with the same e-mail.
        :return: A new user.
        """
        await self.validate_password(user_create.password, user_create)

        existing_user = await self.user_db.get_by_email(user_create.email)
        if existing_user is not None:
            raise exceptions.UserAlreadyExists()

        safe = False
        user_dict = (
            user_create.create_update_dict()
            if safe
            else user_create.create_update_dict_superuser()
        )
        password = user_dict.pop("password")
        user_dict["hashed_password"] = self.password_helper.hash(password)

        created_user = await self.user_db.create(user_dict)

        await self.on_after_register(created_user, request)

        return created_user

    async def authenticate(
            self, credentials: OAuth2PasswordRequestForm
    ):
        """
        Authenticate and return a user following an email and a password.

        Will automatically upgrade password hash if necessary.

        :param credentials: The user credentials.
        """
        try:
            user = await self.get_by_email(credentials.username)
        except exceptions.UserNotExists:
            # Run the hasher to mitigate timing attack
            # Inspired from Django: https://code.djangoproject.com/ticket/20760
            self.password_helper.hash(credentials.password)
            return None
        verified, updated_password_hash = self.password_helper.verify_and_update(
            credentials.password, user.hashed_password
        )
        if not verified:
            return None
        # Update password hash to a more robust one if needed
        if updated_password_hash is not None:
            await self.user_db.update(user, {"hashed_password": updated_password_hash})

        return user

    async def on_after_register(
            self, 
            user: User,
            request: Optional[Request] = None,
            ):
        async with async_session_general() as session:
            session.add(UserQueryCount(
                user_id=user.id,
                query_count=query_value,
                last_update_date=datetime.strptime(datetime.now().strftime(date_format), date_format),
                )
                )
        
            await session.commit()

        print(f"Зарегистрирован пользователь {user.email}")

    async def on_after_login(
        self,
        user: User,
        request: Optional[Request] = None,
        response: Optional[Response] = None,
    ) -> None:
        request.session["config"] = {
            "config_id": -1,
            "database_name": "",
            "access_token": "",
            "user_id": -1,
            "host_id": "",
        }
        request.session["group"] = {
            "group_id": -1,
            "name": "",
        }

    async def on_after_forgot_password(

            self, user: User, token: str, request: Optional[Request] = None

    ):
        print(f"User {user.id} has forgot their password. Reset token: {token}")

    async def on_after_request_verify(

            self, user: User, token: str, request: Optional[Request] = None

    ):
        print(f"Verification requested for user {user.id}. Verification token: {token}")



async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)