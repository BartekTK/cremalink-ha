ARG BUILD_FROM
FROM $BUILD_FROM

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir "cremalink==0.1.0b6"

# Copy data for add-on
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]