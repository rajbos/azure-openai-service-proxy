""" Request Manager base class """

import logging

from fastapi import APIRouter, HTTPException, Request

# pylint: disable=E0402
from ..authorize import Authorize, AuthorizeResponse
from ..config import Config
from ..rate_limit import RateLimit

logging.basicConfig(level=logging.INFO)


class RequestManager:
    """Request Manager base class"""

    def __init__(self, *, authorize: Authorize, config: Config):
        self.authorize = authorize
        self.config = config

        self.router = APIRouter()
        self.rate_limit = RateLimit()
        self.logger = logging.getLogger(__name__)

    async def authorize_request(self, deployment_name: str, request: Request) -> AuthorizeResponse:
        """authorize request"""

        authorize_response = await self.authorize.authorize_api_access(
            headers=request.headers, deployment_name=deployment_name
        )

        if self.rate_limit.is_call_rate_exceeded(authorize_response.user_id):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again in 10 seconds",
            )

        return authorize_response

    async def process_request(
        self,
        *,
        deployment_name: str,
        request: Request,
        model: object,
        call_method: classmethod,
        validate_method: classmethod = None,
    ):
        """authorize request"""
        if validate_method:
            validate_method(model)

        # get the api version from the query string
        if hasattr(model, "api_version"):
            if "api-version" in request.query_params:
                model.api_version = request.query_params["api-version"]

        authorize_response = await self.authorize.authorize_api_access(
            headers=request.headers, deployment_name=deployment_name
        )

        if hasattr(model, "max_tokens"):
            if model.max_tokens is not None and model.max_tokens > authorize_response.max_token_cap:
                model.max_tokens = authorize_response.max_token_cap

        if self.rate_limit.is_call_rate_exceeded(authorize_response.user_id):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again in 10 seconds",
            )

        openai_request = {}

        for key, value in model.__dict__.items():
            if value is not None and key != "api_version":
                openai_request[key] = value

        deployment = await self.config.get_catalog_by_deployment_name(authorize_response)

        response, http_status_code = await call_method(model, openai_request, deployment)

        # log the request usage
        if "usage" in response:
            print(f"usage: {response.get('usage')}")

        return response, http_status_code

    def throw_validation_error(self, message: str, status_code: int):
        """throw validation error"""
        raise HTTPException(
            status_code=status_code,
            detail=message,
        )

    def report_exception(self, message: str, http_status_code: int) -> HTTPException:
        """report exception"""

        self.logger.warning(msg=f"{message}")

        raise HTTPException(
            status_code=http_status_code,
            detail=message,
        )