# Fixed DSL Chinese font runtime

The existing reviewed template runtime remains unchanged. DSL uses a separate image
containing the fixed Noto Sans CJK font. This addresses T037's actual encoded-video
missing-glyph defect, not a change to allowed DSL actions or container permissions.

Inputs:

- Base: `manimcommunity/manim@sha256:89ab433ce59134a4dcf351deb2511e067ab354393c0bb7d1859f3e8f0b2406a3`.
- [Debian official package/checksum](https://packages.debian.org/trixie/all/fonts-noto-cjk/download):
  `fonts-noto-cjk_20240730+repack1-1_all.deb`, SHA256
  `f5dc28a754e17327d99f0a612134d92c8dd6187314ae967cb77f25df60860139`.
- Regular font bytes: SHA256
  `b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a`.
- Actual tested arm64 local image:
  `edumind-dsl-fonts@sha256:e697588b6f06d5730beb6226032501f0ef1a6c93d17ece3c6ab6a58ce7fee69c`.

Download the exact package from Debian separately into an ignored build directory,
verify the official SHA256, copy this Dockerfile there, then build:

```sh
docker build --network none --tag edumind-dsl-fonts:t037-v1 <build-directory>
docker image inspect edumind-dsl-fonts:t037-v1 --format '{{json .RepoDigests}}'
```

`dpkg-deb --extract` copies font data and its bundled license; no package installation
scripts run. Runtime never downloads fonts, mounts host fonts, or executes candidate
code outside its constrained container. The runner checks fixed font bytes, exact
Fontconfig family/file resolution, and every Text character against the SC face's
charset before invoking Manim. Missing/substituted fonts or uncovered glyphs return
`DSL_RENDER_UNAVAILABLE`, preventing publication of tofu text.

The image is local only; it has not been pushed or deployed. Docker image timestamps
and platform selection may produce another digest when rebuilding. Never substitute
a mutable tag for the frozen runtime: independently freeze/admit/qualify any new
image digest and rerun acceptance. Other architectures are not covered by the arm64
measurements. Font/image identity changes invalidate previous DSL candidate/cache
qualification; previous template identities remain intact. Dynamic entry remains
subject to the separate phase acceptance gate.
