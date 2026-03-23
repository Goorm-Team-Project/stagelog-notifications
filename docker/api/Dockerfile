FROM python:3.12.3-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && update-ca-certificates \
    && curl -fsSL https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem -o /etc/ssl/certs/rds-global-bundle.pem \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# 운영환경을 위해 소스 코드 전체를 이미지 안에 넣기
COPY . /app/

# 소스는 volume mount로 개발(빠른 빌드). 운영에서는 COPY 방식으로 변경
EXPOSE 8000

CMD ["sh", "-lc", "python manage.py collectstatic --noinput && gunicorn --bind 0.0.0.0:8000 config.wsgi:application --access-logfile - --error-logfile - --log-level debug --capture-output --timeout 120"]
