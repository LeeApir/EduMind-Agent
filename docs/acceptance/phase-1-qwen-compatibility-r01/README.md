# Qwen 完整审核请求兼容性修复：零调用包

用户授权修复与离线验证；真实兼容性调用须修复评审后另批。本包真实Provider0，无run-approval/当日价格条款签核/私有账本。旧所有停止运行、余槽、余额不恢复；T040 blocked/catalog_only。

## Schema 两层校验

内部能力显式选择qwen-strict-20261017-v1，不根据模型名猜测能力。生产适配器只对该profile生成Qwen传输投影：移除不支持的uniqueItems，按实际引用闭包裁剪$defs（9→1）。未处理的不支持/未知关键字与外部引用发送前拒绝。完整业务Schema保留且只以它校验模型结果；去重/锚点枚举/类别/必填/额外字段等语义不放宽。其他调用默认full-v1不变，未切生产审核或生成默认。政策v4.5、学生材料、Prompt与目标/输入契约不改，能力profile与源码摘要独立绑定。

官方关键字表明确uniqueItems不支持并返回400，旧完整Schema含该词，已证明旧请求不兼容；旧两次400原因不能被追溯确诊为唯一该问题。依据[阿里云文档](https://help.aliyun.com/zh/model-studio/qwen-structured-output)。

## 错误解码

新独立诊断transport读取原始流；原始上限65536字节、解码上限131072字节，gzip/zlib-deflate增量解压使用输出上限。分别记录实际读取字节数/完整性/原始hash，截断、无效压缩、解压炸弹、多成员尾随数据明确拒绝。只请求gzip/deflate，br/复合/未知编码显式unsupported，不误判成非JSON。媒体类型和编码白名单、标准错误字段名称/类型、白名单code与技术词保留（含uniqueItems），原始正文/头/Key/未知字段值不持久化。未知原因不猜测，解码完整性也不等于语义通过。

## 新的最多一次调用（尚未批准）

仅原reachable-safety材料的修正后完整审核请求，非简化探针。生成deepseek-flash保持，审核qwen3.8-max-0902、非思考、strict Schema、8192请求/8202预留、60秒，原超时后仅10秒本地清理。只修改wire Schema和新错误诊断，消息及其他请求参数逐字不变。当前准确wire 33763字节；预算1次/13.283340元，按输入12/输出36元每百万全价保守预留，不假定免费。无重试/纠错/回退/新候选/正式验收。

批准须准确绑定proposal摘要、1次及13.283340元；执行当日另核验价格/能力并写terms日期记录，CLI缺批准在凭据/数据库/私有状态前拒绝。专用PG仍edumind_catalog_qwen_review_20261017，凭据元数据在本新包重绑定，不修改.env。成功只报告COMPATIBLE_PENDING_SEMANTIC_REVIEW并保存真实结果、实际模型、用量和完整性；核对完整性后才逐条核对全部断言与全部引用。失败即停止。无论结果均不发下一条、不恢复旧候选，也不计T040正式质量分。

## 复现

零调用准备：backend/.venv/bin/python scripts/prepare_qwen_compatibility.py --write。
离线单元与Mock：backend/.venv/bin/python -m pytest scripts/tests/test_qwen_compatibility_repair.py scripts/tests/test_qwen_compatibility_runner.py -q；完整5项调度需专用测试PG环境，不读取Provider凭据。真实入口（当前必须拒绝）：backend/.venv/bin/python scripts/run_qwen_compatibility.py --run-one。
