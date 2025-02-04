import os
import refagent

from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import AuthType
from grazie_langchain_utils.language_models.grazie import ChatGrazie
from grazie_langchain_utils.callbacks import GrazieInfoCallbackHandler
from pydantic import SecretStr

def test_grazie():
    grazie_llm = ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                            client_auth_type=AuthType.APPLICATION,
                            client_url=GrazieApiGatewayUrls.STAGING,
                            profile="openai-gpt-4o-mini",
                            client_agent_name='ref-agent',
                            client_agent_version='0.1'
                            )

    print(grazie_llm.invoke("how can langsmith help with testing?"))