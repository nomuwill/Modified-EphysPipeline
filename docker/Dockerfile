FROM python:3.10
ENV DEBIAN_FRONTEND=noninteractive
ENV DASH_DEBUG_MODE=False

RUN python -m pip install --force-reinstall 'git+https://github.com/braingeneers/braingeneerspy.git#egg=braingeneerspy[all]'
RUN set -ex && \
    pip install -r requirements.txt

COPY ./src/top_level.txt /usr/local/lib/python3.10/site-packages/scipy-1.9.3.dist-info/top_level.txt

# PRP setup
ENV ENDPOINT_URL="https://s3-west.nrp-nautilus.io"

# run locally
EXPOSE 8050
CMD ["gunicorn", "-b", "0.0.0.0:8050", "--reload", "app:server"]

COPY ./src /app
WORKDIR /app