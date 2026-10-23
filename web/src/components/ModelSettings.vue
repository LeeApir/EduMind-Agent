<script setup lang="ts">
import { onBeforeUnmount,onMounted,ref,watch } from 'vue';
import { ensureCatalogSession } from '../api/catalog';
import { CAPABILITY_LABELS,getModels,listConnections,type Connection,type ModelList } from '../api/providers';
import { listPreferences,PROFILES,resolveConfiguration,type Preference,type Profile } from '../api/modelPreferences';
import { readOperation,type Operation } from '../api/freeCourses';
import ProviderSettings from './ProviderSettings.vue';
import ModelPreferences from './ModelPreferences.vue';
import WorkspaceState from './WorkspaceState.vue';
const props=withDefaults(defineProps<{active?:boolean;initialPanel?:'overview'|'connections'|'preferences';courseId?:string;operationId?:string}>(),{active:true,initialPanel:'overview',courseId:'',operationId:''});
const emit=defineEmits<{close:[]}>();
const panel=ref(props.initialPanel);const owner=ref('');const loading=ref(true);const error=ref('');const connections=ref<Connection[]>([]);const preferences=ref<Preference[]>([]);const preferencesKnown=ref(false);const selected=ref('');const modelLimit=ref(5);const cache=ref<ModelList>();const cacheLoading=ref(false);const cacheError=ref('');const operation=ref<Operation>();const operationError=ref('');let alive=true;let epoch=0;let cacheEpoch=0;
const providerNames:Record<string,string>={'openai-compatible':'OpenAI-compatible',ollama:'Ollama',anthropic:'Anthropic',gemini:'Google Gemini',spark:'讯飞星火'};
const credentialNames:Record<string,string>={present:'凭据已保存',missing:'尚无凭据',expired:'凭据已到期',revoked:'凭据已撤销'};
function credential(item:Connection):string{return item.credential_mode==='none'?'明确无需密钥':item.credential_mode==='temporary'?'单次临时密钥，不缓存原值':credentialNames[item.credential_state]??'凭据状态未知';}
function target(profile:Profile):string{if(!preferencesKnown.value)return '已保存选择未读到，不能推断为默认配置';const resolved=resolveConfiguration(preferences.value,profile);if(!resolved.preference)return '沿用服务端默认；这里不读取系统密钥';const route=resolved.preference.route;const conn=connections.value.find(c=>c.id===route.connection_id);return `${conn?.display_name??'连接未读到'} / ${route.model_id} · 配置 v${route.config_version}`;}
async function load():Promise<void>{const token=++epoch;loading.value=true;preferencesKnown.value=false;error.value='';operationError.value='';cacheEpoch+=1;cache.value=undefined;cacheLoading.value=false;cacheError.value='';try{const session=await ensureCatalogSession();if(!alive||!props.active||token!==epoch)return;if(owner.value!==session.owner){connections.value=[];preferences.value=[];operation.value=undefined;selected.value='';}owner.value=session.owner;const results=await Promise.allSettled([listConnections(),listPreferences(),props.courseId&&props.operationId?readOperation(props.courseId,props.operationId):Promise.resolve(null)]);if(!alive||!props.active||token!==epoch)return;const [c,p,o]=results;if(c.status==='fulfilled')connections.value=c.value;else{connections.value=[];error.value='连接记录未能读取，不能把读取失败当作未配置。';}if(p.status==='fulfilled'){preferences.value=p.value;preferencesKnown.value=true;}else{preferences.value=[];error.value+=' 已保存档位未能读取，不根据空缓存推断默认选择。';}if(o.status==='fulfilled')operation.value=o.value??undefined;else{operation.value=undefined;operationError.value='当前操作状态未能读取；不会用最新设置倒推原操作的模型。';}const first=connections.value.find(c=>c.id===selected.value)??connections.value[0];if(first)await choose(first);else selected.value='';}catch{if(alive&&token===epoch){error.value='当前学习身份或设置未能读取，请重试。';connections.value=[];preferences.value=[];operation.value=undefined;}}finally{if(alive&&token===epoch)loading.value=false;}}
async function choose(connection:Connection):Promise<void>{const token=++cacheEpoch;selected.value=connection.id;modelLimit.value=5;cache.value=undefined;cacheError.value='';cacheLoading.value=true;try{const value=await getModels(connection);if(alive&&props.active&&token===cacheEpoch)cache.value=value;}catch{if(alive&&props.active&&token===cacheEpoch)cacheError.value='缓存型号未能读取；读取缓存不会联网更新或探测服务。';}finally{if(alive&&token===cacheEpoch)cacheLoading.value=false;}}
function show(value:'overview'|'connections'|'preferences'):void{panel.value=value;if(value==='overview'&&props.active)void load();}
watch(()=>props.initialPanel,value=>{panel.value=value;});
watch(()=>props.active,value=>{if(value)void load();else{epoch+=1;cacheEpoch+=1;loading.value=false;cacheLoading.value=false;}});
onMounted(load);onBeforeUnmount(()=>{alive=false;epoch+=1;cacheEpoch+=1;});
</script>
<template>
  <main class="page-view model-settings">
    <p class="page-eyebrow">
      工具按你的选择工作
    </p><h1>模型设置</h1><p class="page-lead">
      保存用于下一次新操作。已开始的课程与导师操作继续使用开始时固定的配置，不自动重启或回退。
    </p><div class="action-row">
      <button
        class="secondary"
        type="button"
        @click="emit('close')"
      >
        ← 返回原页面
      </button><button
        class="secondary"
        type="button"
        :disabled="loading"
        @click="load"
      >
        重新读取设置概览
      </button>
    </div>
    <div class="settings-notice surface">
      <h2>配置、能力与真实验收分别记录</h2><p>已配置不等于可连通；缓存能力需看来源与配置版本，服务声明不当作独立验收。本页不承诺课程质量或其他厂商真实接入已验收。</p><p>读取缓存和保存配置不会探测服务。主动测试/更新模型可能产生请求与费用，仍须走已有明确同意与授权流程；不会恢复旧验证预算。</p><p v-if="operation">
        已读取原操作 {{ operation.kind==='tutor_turn'?'导师提问':'课程生成/修订' }} 的状态：{{ ({queued:'排队中',running:'进行中',cancel_requested:'正在停止',succeeded:'成功',partially_succeeded:'部分完成',awaiting_clarification:'等待澄清',failed:'失败',cancelled:'已停止',timed_out:'超时'} as Record<string,string>)[operation.state]??'状态待核对' }}。这里修改设置不替换它的配置。
      </p><p
        v-if="operationError"
        role="status"
      >
        {{ operationError }}
      </p><p>凭据仅显示保护状态，系统密钥不在此读取。离开连接面板会清空未提交的密钥，其他未保存表单选择保留。</p>
    </div>
    <nav
      class="action-row"
      aria-label="模型设置区域"
    >
      <button
        class="secondary"
        type="button"
        :aria-pressed="panel==='overview'"
        @click="show('overview')"
      >
        设置概览
      </button><button
        class="secondary"
        type="button"
        :aria-pressed="panel==='connections'"
        :disabled="loading || !owner"
        @click="show('connections')"
      >
        管理连接与凭据
      </button><button
        class="secondary"
        type="button"
        :aria-pressed="panel==='preferences'"
        :disabled="loading || !owner"
        @click="show('preferences')"
      >
        管理档位与数据去向
      </button>
    </nav>
    <WorkspaceState
      v-if="loading"
      kind="loading"
      detail="正在读取设置与已有缓存，没有探测或模型调用。"
    /><p
      v-if="error"
      role="alert"
    >
      {{ error }}
    </p>
    <section
      v-show="panel==='overview'"
      class="settings-overview"
    >
      <div class="settings-grid">
        <section
          class="surface settings-section"
          aria-label="连接配置概览"
        >
          <h2>连接与保护状态</h2><p v-if="!loading && !error && !connections.length">
            未配置用户连接。服务端默认连接不需要在这里输入或显示系统 Key。
          </p><article
            v-for="item in connections"
            :key="item.id"
            class="connection-summary"
          >
            <h3>{{ item.display_name }}</h3><p>{{ providerNames[item.provider_type] }} · {{ item.enabled?'已配置并启用':'已配置但停用' }} · 配置 v{{ item.config_version }}</p><p>{{ credential(item) }}</p><p>真实接入与教学质量需独立核对，不由“启用”标记保证。</p><button
              class="secondary"
              type="button"
              :disabled="cacheLoading"
              @click="choose(item)"
            >
              读取{{ item.display_name }}的能力缓存
            </button>
          </article>
        </section>
        <section
          class="surface settings-section"
          aria-label="缓存能力概览"
        >
          <h2>型号与能力缓存</h2><p
            v-if="cacheLoading"
            role="status"
          >
            正在读取已保存的能力缓存。
          </p><p
            v-if="cacheError"
            role="alert"
          >
            {{ cacheError }}
          </p><p v-if="!selected && !cacheLoading">
            选择连接后可只读查看缓存；这里不自动联网获取型号。
          </p><p v-if="cache">
            缓存对应配置 v{{ cache.config_version }} · {{ cache.refreshed_at??'尚无更新时间' }}
          </p><p v-if="cache && !cache.models.length">
            缓存未列出型号；不能据此认定服务没有模型。
          </p><article
            v-for="model in (cache?.models??[]).slice(0,modelLimit)"
            :key="model.id"
            class="capability-summary"
          >
            <h3>{{ model.id }}</h3><p>能力来源：{{ model.capabilities.source==='verified'?'已有探测记录，非教学验收':model.capabilities.source==='declared'?'服务声明，未作独立验证':'未知' }} · {{ model.capabilities.version }}</p><dl>
              <template
                v-for="(label,flag) in CAPABILITY_LABELS"
                :key="flag"
              >
                <dt>{{ label }}</dt><dd>{{ model.capabilities[flag]===true?'支持标记':model.capabilities[flag]===false?'不支持':'未知' }}</dd>
              </template>
            </dl>
          </article>
        </section>
      </div>
      <section
        class="surface settings-section"
        aria-label="已保存模型档位"
      >
        <h2>下一次新操作的档位选择</h2><p>各档位保留已保存的服务、型号与数据去向。敏感上下文只发送到明确选择且同意的目标。</p><article
          v-for="(label,profile) in PROFILES"
          :key="profile"
          class="preference-summary"
        >
          <h3>{{ label }}</h3><p>{{ target(profile) }}</p><p v-if="resolveConfiguration(preferences,profile).preference">
            {{ resolveConfiguration(preferences,profile).preference!.state==='available'?'配置有效，连通性与能力另验':resolveConfiguration(preferences,profile).preference!.state==='consent_required'?'配置已变化，需重新同意':'选择不可用，不自动降级' }}
          </p><p>回退：{{ !preferencesKnown?'尚未读到回退设置':resolveConfiguration(preferences,profile).preference?.fallbacks.length?`仅按已保存的 ${resolveConfiguration(preferences,profile).preference!.fallbacks.length} 项明确选择及错误类型执行`:'未启用用户回退' }}</p>
        </article>
      </section>
    </section>
    <section
      v-show="panel==='connections'"
      class="surface settings-section settings-editor"
    >
      <ProviderSettings
        v-if="owner"
        :key="`connections:${owner}`"
        embedded
        :visible="active && panel==='connections'"
        @close="emit('close')"
      />
    </section><section
      v-show="panel==='preferences'"
      class="surface settings-section settings-editor"
    >
      <ModelPreferences
        v-if="owner"
        :key="`preferences:${owner}`"
        embedded
        @close="emit('close')"
      />
    </section>
  </main>
</template>
