import os
from functools import lru_cache

from pydantic.v1 import BaseSettings


class Settings(BaseSettings):
    # NOTE:
    # The default value is set for the development environment.
    # Overridden by environment variables.
    env: str = 'local'
    aws_access_key_id: str = 'localstack'
    aws_secret_access_key: str = 'localstack'
    aws_region_name: str = 'ap-northeast-1'
    es_host: str = 'http://localhost:9200'
    es_api_key: str = ''
    openai_api_key: str = ''
    openai_org_id: str = ''
    openai_project_id: str = ''

    class Config:
        # https://pydantic-docs.helpmanual.io/usage/settings/#dotenv-env-support
        env_file = '.env'
        env_file_encoding = 'utf-8'


@lru_cache
def get_settings():
    return Settings()
