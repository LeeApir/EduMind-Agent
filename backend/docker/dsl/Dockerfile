FROM manimcommunity/manim@sha256:89ab433ce59134a4dcf351deb2511e067ab354393c0bb7d1859f3e8f0b2406a3
USER root
COPY fonts-noto-cjk.deb /tmp/fonts-noto-cjk.deb
RUN echo 'f5dc28a754e17327d99f0a612134d92c8dd6187314ae967cb77f25df60860139  /tmp/fonts-noto-cjk.deb' | sha256sum -c - \
    && dpkg-deb --extract /tmp/fonts-noto-cjk.deb / \
    && rm /tmp/fonts-noto-cjk.deb \
    && fc-cache -f
USER 10001:10001
