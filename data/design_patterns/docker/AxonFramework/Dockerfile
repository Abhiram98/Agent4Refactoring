FROM ubuntu:24.04

# Avoid tzdata prompts
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y openjdk-21-jdk maven git dos2unix && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone --depth 1 https://github.com/AxonFramework/AxonFramework.git .

COPY run_build.sh run_test.sh /app/

RUN dos2unix /app/run_build.sh /app/run_test.sh && \
    chmod +x /app/run_build.sh /app/run_test.sh

CMD ["/bin/bash"]
