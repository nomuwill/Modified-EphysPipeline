FROM python:3.12
ENV DEBIAN_FRONTEND=noninteractive
ENV DASH_DEBUG_MODE=False

RUN apt-get update && apt-get install -y time \
    libxt-dev \
    curl \
    git \
    wget \
    build-essential\
    awscli\
    zip\
    time\
    glances\
    pv

RUN pip install "braingeneers[iot,analysis,data]"
RUN pip install deprecated \ 
    matplotlib \
    tqdm

# PRP setup
ENV ENDPOINT_URL="https://s3.braingeneers.gi.ucsc.edu"

COPY src/ /app
RUN chmod +x /app/start_splitter.sh

WORKDIR /app


# surygeng/maxtwo_splitter:v0.1