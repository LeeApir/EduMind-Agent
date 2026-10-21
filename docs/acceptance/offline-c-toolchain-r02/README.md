# T066 固定 C 工具链锁 r02

原ADR0019及[快照补充批准](../../ADR/0019-toolchain-amendment-approval-20261019.json)共同授权。原失败/候选模拟保持原样，本目录仅记录新实际准备结果。

官方签名2026-06-01 trixie索引验证成功，精确复核已批准的32包计划且无基础包升级/降级后下载46.6MB；逐包大小/SHA-256见 packages.json，签名元数据摘要见 lock.json。缓存位于 `/tmp/edumind-t066-toolchain-r02`，不提交二进制包或读取项目/用户凭据。

构建只含固定Dockerfile、已校验debs、可信controller；`docker build --network=none --pull=false` 使用原基础镜像安装缓存包，没有任何课程样本或项目挂载。实际下载/构建记录见 download.txt / build.txt；工具链包版本及最终image ID见 lock.json。

在原批准的非特权、禁网、只读、限额容器配置内，仅运行controller metadata及clang/ld/dpkg版本查询，原始有界结果见 metadata.json。实际Clang19.1.7、GNU ld2.44、Linux aarch64，Python3.14.7来自固定基础镜像；libc6仍2.41-12+deb13u3。Python用于此独立受信控制器，不改变后端Python3.11约定。

本阶段样本编译/执行与Provider调用均0。**这些版本查询不等于隔离探针通过或C程序通过**。T067必须核对实际容器inspect和有效限制、运行安全探针，才可执行原件固定矩阵。控制器或镜像后续如需实现新增固定case，必须新建锁版本及独立运行证据，保留本锁，不能原地改写本次镜像或元数据。

重建时先按批准的官方快照、精确包计划和签名验证重新取得32包，逐包摘要匹配，再将 `scripts/offline_c_runtime/Dockerfile`、controller及debs复制到无源码/凭据的最小私有构建目录，执行lock.json所记离线构建命令。镜像ID如不同不能直接冒充本锁运行，应记录实际新构建与摘要差异。环境不可用时停止，不用宿主编译器回退。
