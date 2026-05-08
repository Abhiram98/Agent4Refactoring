FROM ubuntu:24.04

# Avoid tzdata prompts
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y openjdk-17-jdk maven git dos2unix && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone --depth 1000 https://github.com/apache/hbase.git

# RUN git fetch --depth 1 origin 2e42e4cdc9dbf8774aa63c305f024d5b16e3b5a4
RUN cd hbase && git checkout 2e42e4cdc9dbf8774aa63c305f024d5b16e3b5a4 # this is the current HEAD commit on my repo.

COPY run_build.sh run_test.sh apply_patch.sh refactor.patch /app/

RUN dos2unix /app/run_build.sh /app/run_test.sh /app/apply_patch.sh && \
    chmod +x /app/run_build.sh /app/run_test.sh /app/apply_patch.sh

CMD ["/bin/bash"]
