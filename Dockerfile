FROM python:3.12-slim
RUN pip install --no-cache-dir https://github.com/digitalgp/listarr/archive/refs/heads/main.zip paho-mqtt==2.1.0 tzdata
COPY listarr_mqtt.py /app/listarr_mqtt.py
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/listarr_mqtt.py"]
