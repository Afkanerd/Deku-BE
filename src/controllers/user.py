"""Controller Functions for User Operations"""

import logging
from typing import Optional, Dict, Union

from playhouse.shortcuts import model_to_dict

from src.security.crypto import DataSecurity
from src.orm.peewee.handlers.user import UserHandler
from src.utils import rabbitmq

logger = logging.getLogger(__name__)


def encrypt_user_data(user: dict) -> dict:
    """
    Encrypt sensitive data in a user dictionary.

    :param user: dict - The user dictionary to encrypt.

    :return: dict - The encrypted user dictionary.
    """
    data_security = DataSecurity()
    keys_to_encrypt = [
        "first_name",
        "last_name",
        "phone_number",
        "twilio_account_sid",
        "twilio_auth_token",
        "twilio_service_sid",
    ]

    for key in keys_to_encrypt:
        if key in user:
            user[key] = data_security.encrypt_data(plaintext=user[key])

    return user


def decrypt_user_data(user: dict) -> dict:
    """
    Decrypts sensitive data in a user dictionary.

    :param user: dict - The user dictionary to decrypt.

    :return: dict - The decrypted user dictionary.
    """
    data_security = DataSecurity()
    keys_to_encrypt = [
        "first_name",
        "last_name",
        "phone_number",
        "twilio_account_sid",
        "twilio_auth_token",
        "twilio_service_sid",
    ]

    for key in keys_to_encrypt:
        if key in user:
            user[key] = data_security.decrypt_data(ciphertext=user[key])

    del user["password"]

    return user


def create_user(email: str, password: str, **kwargs) -> Optional[Dict]:
    """
    Creates a new user in the database and RabbitMQ, returns the new user object as a dictionary

    :param email: str - user email address
    :param password: str - user password
    :param kwargs: dict - additional user fields

    :return: dict - the newly created user object
    """
    data_security = DataSecurity()
    user_handler = UserHandler()

    user_data = encrypt_user_data(user=kwargs)

    new_user = user_handler.create_user(
        email=email,
        password=data_security.hash_password(password=password),
        **user_data
    )

    if new_user:
        try:
            if rabbitmq.create_virtual_host(name=new_user.account_sid):
                if rabbitmq.create_user(
                    username=new_user.account_sid,
                    password=new_user.auth_token,
                    tags="management",
                ):
                    rabbitmq.set_permissions(
                        configure=".*",
                        write=".*",
                        read=".*",
                        username=new_user.account_sid,
                        virtual_host=new_user.account_sid,
                    )

        except Exception as error:
            # Rollback changes.
            rabbitmq.delete_user(username=new_user.account_sid)
            rabbitmq.delete_virtual_host(name=new_user.account_sid)
            new_user.delete_instance()

            raise error

    return new_user


def verify_user(email: str, password: str) -> Optional[Dict]:
    """
    Verifies a user's email and password and returns the user object as a dictionary

    :param email: str - user email address
    :param password: str - user password

    :return: dict - the user object as a dictionary or None if verification failed
    """
    data_security = DataSecurity()
    user_handler = UserHandler()

    [total, users_list] = user_handler.get_users_by_field(email=email)

    if total < 1 and len(users_list) < 1:
        logger.error("User %s not found.", email)
        return None

    user = users_list[0]

    if not data_security.check_password(
        hashed_password=user.password, password=password
    ):
        logger.error("Wrong password for user %s", email)
        return None

    return model_to_dict(user)


def get_user_by_id(user_id: int) -> dict:
    """
    Retrieve a user by ID.

    :param user_id: int - The unique identifier for the user.

    :return: dict - A dictionary representing the retrieved user with decrypted data.
    """
    user_handler = UserHandler()

    user = user_handler.get_user_by_id(user_id=user_id)

    if user:
        user = model_to_dict(user)
        user = decrypt_user_data(user)

    return user


def update_user(user_id: int, **kwargs: dict) -> Dict[str, Union[int, str]]:
    """
    Update a user by ID.

    :param user_id: int - The ID of the user to update.
    :param kwargs: dict - Optional keyword arguments for updating user attributes.

    :return: dict - A dictionary representing the updated user with decrypted data.
    """
    user_handler = UserHandler()

    user_data = encrypt_user_data(user=kwargs)
    user = user_handler.update_user(user_id=user_id, **user_data)
    user = model_to_dict(user)
    user = decrypt_user_data(user)

    return user
