ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}

WORKDIR /app

COPY . .

RUN unzip libs/grazie-langchain-utils.zip -d libs/

RUN python -m pip install libs/grazie-langchain-utils

RUN python -m pip install -e .

ENTRYPOINT ["python", "-m", "refagent"]

#default args to entrypoint.
CMD ["--help"]