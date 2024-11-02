FROM python:3.10
ENV DEBIAN_FRONTEND=noninteractive
ENV DASH_DEBUG_MODE=False

RUN pip install braingeneers['iot','analysis','data']
COPY docker/requirements.txt ./src/requirements.txt
RUN set -ex && \
    pip install -r ./src/requirements.txt

#COPY src/initial_dictionary /src/initial_dictionary
COPY docker/top_level.txt /usr/local/lib/python3.10/site-packages/scipy-1.10.1.dist-info/top_level.txt

# PRP setup
ENV ENDPOINT_URL="https://braingeneers.gi.ucsc.edu"

# run locally
EXPOSE 8050
#CMD ["gunicorn", "-b", "0.0.0.0:8050", "--reload", "app:server"]
CMD ["gunicorn", "--timeout", "1000", "--workers=1","-b", "0.0.0.0:8050", "--reload", "app:server"]


COPY src/ /app
WORKDIR /app

# surygeng/maxwell_dashboard:v0.1