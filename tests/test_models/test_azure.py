from langchain_openai import AzureChatOpenAI
import refagent

def test_azure_chat():
    model = AzureChatOpenAI(
        azure_deployment='gpt-4o-mini',
        api_version='2025-01-01-preview',
        temperature=0,
    )
    response = model.invoke("What is a rename refactoring?")
    print(response)