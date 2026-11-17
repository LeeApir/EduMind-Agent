# T033 模型设置整合

ModelSettings统一概览/连接管理/档位及数据去向，复用现有ProviderSettings、ModelPreferences和原API；不新增Provider、模型名称硬依赖、角色专属档位或真实调用。概览分开展示配置启用/凭据保护、准确config_version对应缓存、能力来源与未知/不支持、已有配置state及显式回退。读取偏好失败不显示成默认选择/未启用回退；缓存失败不显示成没有模型，缓存型号分批显示。探测记录不当作教学或其他厂商独立验收。

原连接表单/版本校验、SSRF/凭据生命周期、显式探测同意及模型偏好同意流程保留；只新增embedded语义标签/样式和visible控制：离开连接面板/设置页清空未提交密钥和探测同意，保留非秘密表单。概览仅GET，保存仅配置元数据，仍不授予真实预算或恢复旧验证额度；现有操作沿开始时冻结配置，不替换/重启/静默回退。当前操作只读显示状态，不从最新偏好倒推其具体模型。设置刷新保留返回页及准确课程位置，不保存密钥。

实际：`pnpm --dir web exec vitest run`40文件 **292通过，0失败/跳过**，新增model-settings-redesign8项，原provider17/preference11及导航9保持通过；typecheck/build通过，lint0错误35既有ProfileCard警告，相关5文件定向eslint无警告。覆盖配置/声明能力/不支持/独立验收边界、读取失败不冒充默认、清密钥保留表单/无存储泄漏、owner变化/错误消息关闭、保存不探测不改变原操作、同意后保存无隐式回退、缓存失败及刷新准确返回。首次新Mock误将原连接更新设为PUT，改为原API真实PATCH；未改变接口或削弱断言。

浏览器命令：`backend/.venv/bin/python /Users/apir/.agents/skills/webapp-testing/scripts/with_server.py --server 'pnpm --dir web dev --host 127.0.0.1 --port 5190' --port 5190 -- backend/.venv/bin/python docs/design/phase-1.5-model-settings-t033/browser_check.py`通过。真实Chromium/业务HTTP明确Mock，1440/1024/850/620/390/320分别检查概览/连接/偏好三块无横向溢出；清除未发送密钥、非秘密草稿保留、显式metadata PATCH及consented PUT各1次、无probe/fallback/课程生成、刷新返回准确位置通过。首次浏览器Mock把清单GET误答成SceneProjection，修正夹具后完整通过，业务代码未放宽响应验证。截图/tmp/edumind-p15-t033，1440概览/320连接面板已视检；不计真实PG/连接/教学质量或性能成绩。

41批准/manifest、50历史原件及用户原README SHA、工作流/diff核对通过。没有真实凭据/Provider探测/费用，生产catalog_only、H及旧blocked保持，无push/merge/部署。下一T034全站响应式/可访问性整合，阶段持续目标未完成。
