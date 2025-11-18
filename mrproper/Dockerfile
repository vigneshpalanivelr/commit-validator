FROM artifact.internal.com:6555/ubuntu:20.04

ADD sources.list /etc/apt/sources.list

RUN mkdir -p /root/.pip && \
    echo '[global]' > /root/.pip/pip.conf && \
    echo 'index-url = https://artifact.internal.com/artifactory/api/pypi/pypi/simple' >> /root/.pip/pip.conf && \
    echo 'trusted-host = artifact.internal.com' >> /root/.pip/pip.conf

RUN ls -l /etc/apt/sources.list.d/ \
 && grep -i deadsnakes /etc/apt/sources.list.d/* || true

RUN rm -f /etc/apt/sources.list.d/*deadsnakes* \
 && rm -f /etc/apt/sources.list.d/*Deadsnakes* \
 && apt-get update

RUN rm -f /etc/apt/sources.list.d/deadsnakes-ppa-*.list \
 && apt-get update

RUN apt-get update && apt-get install -y python3 python3-requests git wget python3-setuptools python3-pip
RUN wget -O/tmp/cf.deb https://jenkins.internal.com/debian/dists/squeeze/non-free/binary-amd64/sv-clang-format_7.0sv1-3_amd64.deb && dpkg -i /tmp/cf.deb

RUN mkdir /src
ADD . /src/

# Install Python dependencies from requirements.txt
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt

# Install the mrproper package
RUN cd /src; python3 ./setup.py install

RUN useradd -ms /bin/bash mrcheck
USER mrcheck
WORKDIR /home/mrcheck

RUN git config --global user.email "jenkins@internal.com"
RUN git config --global user.name "Jenkins"
