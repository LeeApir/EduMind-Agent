# fixed-c-offline-v1：输入、隔离和结果协议

状态：T065 Proposed。只有 ADR-0019 具体批准并完成 T066 逐文件审阅及最终工具链锁后才可运行。

## 输入与绑定

输入包最多 2 MiB、最多 32 个普通文件、单文件最多 1 MiB。拒绝软/硬链接、设备、绝对路径、`..`、未列出的文件；不解压任意上传包。只从批准来源复制已审阅 C 字节/片段、驱动、规格，原课程/候选 JSON 留作服务端审计，不挂载整个资料目录。包摘要绑定规范版本、来源摘要、提取映射、驱动、独立规格、预期矩阵和审阅登记；工具链/controller 的最终摘要独立绑定每次结果。

原件只读且不修复。驱动不连接 Provider/数据库，不读取环境中的用户数据。新增驱动的代码审阅在 T066 产生真实记录，不能事先在本提案伪造。只接收 source_id/case_id 枚举，禁止外部 shell 字符串、任意 flags、include 路径、插件或链接脚本。编译 argv 由 controller 固定构造，`subprocess` 不启用 shell。

## 容器与命令

提案启动形态（不是当前可执行命令，最终 image ID/controller 要在 T066 建立）：

```text
docker run --pull=never --name <unique-run-case>
  --network=none --ipc=none --user=10001:10001
  --cap-drop=ALL --security-opt=no-new-privileges:true
  --read-only --cpus=1 --memory=512m --memory-swap=512m --pids-limit=64
  --ulimit=core=0:0 --ulimit=nofile=128:128 --ulimit=fsize=16777216:16777216
  --tmpfs=/work:rw,exec,nosuid,nodev,size=134217728,uid=10001,gid=10001,mode=0700
  --tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16777216,uid=10001,gid=10001,mode=0700
  --mount=type=bind,source=<validated-private-bundle>,target=/bundle,readonly
  --log-driver=none --entrypoint=/usr/bin/env <frozen-image-id>
  -i PATH=/usr/bin:/bin HOME=/tmp TMPDIR=/tmp LANG=C LC_ALL=C
  ASAN_OPTIONS=detect_leaks=0:abort_on_error=1:symbolize=0
  UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=0
  /usr/local/bin/python3 -I /opt/fixed-c/controller.py <registered-source-id> <registered-case-id>
```

T066 必须核实基础层 `/usr/local/bin/python3` 及实际 Python 版本，并将其固定入工具链锁；不存在时阻塞，不悄悄调用宿主解释器。

controller 是受信代码，进入镜像且参与摘要；不能由样本包提供/覆盖。继承 Docker 默认 seccomp，不允许 unconfined、特权、host PID/IPC/net、ptrace、额外 capability 或 Docker socket。容器环境通过 `env -i` 清空后只设置以上常量，不读取宿主 API key、用户 HOME、Git、SSH、`.env` 或 Docker 配置。宿主 supervisor 只需调用 Docker CLI 的最小基础环境，不把配置目录挂入容器。

来源绑定目录在宿主私有运行目录创建，复制后再次摘要并只读挂载；运行前后均核对文件。每 case 独立容器/独立 tmpfs，不复用二进制。controller 先编译到 `/work`，编译成功再以固定 argv 启动样本子进程；原程序与 wrapper/接口是不同 case，不改原程序以取得可执行文件。

编译基线：`/usr/bin/clang-19 -std=c11 -Wall -Wextra -Wpedantic -Wnewline-eof [-Werror] <registered.c> -o /work/program`。

Sanitizer case 额外固定 `-O0 -g -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=all`；fault case 使用普通警告级，以免已知原件末尾换行警告使实际内存测试根本没有执行。严格失败仍独立保留。不得因失败临时删旗标/改源码再称同一 case 通过。

| 限制 | 上限及处理 |
| --- | --- |
| CPU/物理内存 | 1 CPU，512 MiB，总 swap 不增加；inspect 不符即不运行 |
| PID/描述符/单文件 | 64/128/16 MiB；rootfs 与包只读 |
| 单次编译墙钟 | 30 秒，超时杀容器，原定运行 not_run |
| 单次样本墙钟 | 5 秒，超时杀容器 |
| 每 case 容器总墙钟 | 40 秒（含编译与启动）；宿主独立计时，不能依赖样本 timeout |
| stdout/stderr | 每个阶段、每条流最多 65536 字节；并发排空，超出杀容器，保存边界内原字节及 output_limit 状态，不能截断后算 pass |
| 工作磁盘 | `/work`128 MiB、`/tmp`16 MiB tmpfs；无其他可写宿主挂载 |
| controller结果通道 | 宿主另限制容器stdout结果JSON为1 MiB、stderr为64 KiB，超过即杀容器并判protocol_error；该上限不放宽子进程每阶段每流64 KiB限制 |
| 整次运行 | 最多 64 次编译、40 次样本子进程、1200 秒总窗，无自动重试；编译失败不凑运行数 |

正常退出、超时、宿主异常和中断都尝试 `docker kill`/`docker rm -f` 本次确切名字，不清理其他容器。残留无法清理须记录容器名并阻塞下一执行。保留有界日志、控制器结果和摘要，不保留可执行文件或提交生成二进制。

预检使用本地固定的小探针验证：UID/GID/cap/禁止提权、网络 namespace 无非 loopback 路由、只读包和根、实际 cgroup/inspect 限额、输出洪泛和无限循环被宿主终止。仅探针也需按同隔离运行。ASan/UBSan 编译或运行不可用记 unsupported，不冒充源码失败；不移除隔离或在宿主回退。

## 结果结构（必需项）

每个 case 一个 JSON 对象，根额外字段拒绝；运行包另存索引及最终根摘要。所有时间戳 UTC ISO8601，耗时用单调时钟。缺失/不可达数据用明确 null，不填 0 假装已观察。

| 字段 | 类型与含义 |
| --- | --- |
| `version`, `run_id`, `case_id`, `source_id` | 固定版本 fixed-c-offline-v1 和唯一身份 |
| `bindings` | 对象：package/source/extraction/driver/spec/review_registry/toolchain/controller SHA-256，baseline Git commit；不适用 driver 用 null |
| `toolchain` | 对象：image ID、base digest、linux/arm64、clang/linker/libc/runtime 实际版本、包锁摘要；不可只写镜像标签 |
| `isolation` | 对象：实际 inspect 摘要、预检记录摘要、有效配置/limits、清理结果，不保存敏感环境 |
| `kind` | strict_compile / ordinary_compile / sanitizer_compile / original_main / wrapped_main / function_contract / controlled_negative / isolation_probe |
| `fault_at` | 0/1/2/3 或 null；0 明确不注入 |
| `commands` | 有序阶段数组，每项必须有 argv 字符串数组、只允许 /work 的 cwd、固定非敏感 env、开始/结束、duration_ms、exit_code或signal、timeout/output_limit/OOM标志、stdout/stderr 原字节 base64、字节长度、SHA-256；未启动阶段不得伪造退出码 |
| `status`, `reason` | status 为 pass/fail/not_run/unsupported；reason 固定枚举 success、compile_error、runtime_error、assertion_failed、numeric_mismatch、format_mismatch、timeout、output_limit、oom、compile_failed、dependency_missing、sanitizer_unavailable、isolation_unavailable、binding_mismatch、protocol_error、stopped |
| `observations` | 对象：numeric_sequence、format_exact、attempts、allocated、released、live、per_insert_states、free_call_sequence、caller_head_reset、asan、ubsan、lsan；每项 status/evidence 引用明确，未测为 null/not_run |
| `expected_observation_matched` | boolean/null：结果是否符合预先规格，不能用于把程序 fail 改成 pass；尚未运行用 null |
| `scope_limitations` | 字符串数组：只限已运行固定路径，显式指出 tracker/LSan、派生驱动/原 main、编译/语义的界限 |

允许多个检查各自有结果，不用单一总体 pass 抹平格式不符、普通/严格差异或旧失败。Sanitizer 报错时只报告实际诊断，异常终止前没读到的释放计数保持 unknown。使用已审阅 wrapper 的断言及逐分配 tracker 事件交叉验证，不能只匹配 stdout 的 PASS 字符串。

聚合索引须列全部预定 case，未发项写 not_run/stopped，来源问题与环境不支持分开。入库/发布不在此协议：T069 仅生成离线报告，不调用 ReviewAgent、decide_case、publish 或掌握度写入。
