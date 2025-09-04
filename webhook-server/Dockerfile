FROM artifact.internal.com:6555/python:3-alpine

RUN echo "https://artifact.internal.com/artifactory/alpine/v3.20/main" > /etc/apk/repositories && \
    echo "https://artifact.internal.com/artifactory/alpine/v3.20/community" >> /etc/apk/repositories && \
    wget -O /etc/apk/keys/apline-rsa.rsa.pub http://artifact.internal.com/artifactory/api/security/keypair/public/repositories/alpine

RUN mkdir -p '/root/.pip' && echo '[global]' > /root/.pip/pip.conf && echo 'index-url = https://artifact.internal.com/artifactory/api/pypi/pypi/simple' >> /root/.pip/pip.conf && echo 'trusted-host = artifact.internal.com' >> /root/.pip/pip.conf

RUN apk add docker-cli
RUN pip install tornado pyyaml

ADD server.py /srv/server.py

EXPOSE 9912

CMD python3 /srv/server.py
