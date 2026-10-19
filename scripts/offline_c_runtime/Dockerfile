FROM manimcommunity/manim@sha256:89ab433ce59134a4dcf351deb2511e067ab354393c0bb7d1859f3e8f0b2406a3
USER root
COPY debs/ /tmp/fixed-c-debs/
RUN dpkg -i /tmp/fixed-c-debs/*.deb && rm -rf /tmp/fixed-c-debs
COPY controller.py /opt/fixed-c/controller.py
USER 10001:10001
