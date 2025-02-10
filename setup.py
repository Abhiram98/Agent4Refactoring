from setuptools import setup

setup(
   name='refagent',
   version='1.0',
   description='Refactoring agent!',
   author='Abhiram Bellur',
   author_email='bellur.abhiram@gmail.com',
   packages=['refagent'],
   install_requires=[
      'langgraph',
      'langchain',
      'grazie_api_gateway_client @ https://packages.jetbrains.team/pypi/p/grazi/jetbrains-ai-platform-public/download/grazie-api-gateway-client/0.1.9/grazie_api_gateway_client-0.1.9-py3-none-any.whl'
   ],

)