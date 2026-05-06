FROM ubuntu:24.04

# Avoid tzdata prompts
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y openjdk-17-jdk maven git dos2unix && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone --depth 1 https://github.com/apache/flink.git
RUN cd flink && git remote add abhiram_origin https://github.com/Abhiram98/flink.git
RUN cd flink && git fetch --all
RUN cd flink && git pull --all

COPY run_build.sh run_test.sh /app/

RUN dos2unix /app/run_build.sh /app/run_test.sh && \
    chmod +x /app/run_build.sh /app/run_test.sh

CMD ["/bin/bash"]
