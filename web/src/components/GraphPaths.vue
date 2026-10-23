<script setup lang="ts">
import { computed,onBeforeUnmount,onMounted,ref } from 'vue';
import { ensureCatalogSession,loadCatalog,type CatalogListing } from '../api/catalog';
import { PathRequestError,loadGraph,loadGraphVersion,loadMastery,loadCurrentPath,planPath,replanPath,type GraphSnapshot,type MasterySnapshot,type LearningPath } from '../api/paths';
import { readCourse,readManifest,readStored,writeStored,type Manifest } from '../api/freeCourses';
import WorkspaceState from './WorkspaceState.vue';
const props=withDefaults(defineProps<{courseId?:string;courseVersion?:number}>(),{courseId:'',courseVersion:1});
const emit=defineEmits<{goal:[value:string];catalog:[]}>();
const owner=ref('');const graph=ref<GraphSnapshot>();const currentGraph=ref('');const requestedGraph=ref('');const mastery=ref<MasterySnapshot>();const catalog=ref<CatalogListing>();const path=ref<LearningPath|null>(null);const selectedId=ref('');const targetId=ref('');const view=ref<'graph'|'list'>('graph');const loading=ref(true);const busy=ref(false);const error=ref('');const pathError=ref('');const evidenceError=ref('');const courseError=ref('');const originalGoal=ref('');const courseManifest=ref<Manifest>();let alive=true;let sequence=0;
interface Pending {kind:'plan'|'replan';target:string;key:string;expected?:number}
const pending=ref<Pending>();
const key=()=>`edumind:graph:${owner.value}`;
const selected=computed(()=>graph.value?.nodes.find(n=>n.id===selectedId.value));
const historical=computed(()=>Boolean(graph.value&&currentGraph.value!==graph.value.graph_version));
const signed=computed(()=>catalog.value?.releases.find(r=>r.nodes.some(n=>n.id===selectedId.value)));
function name(id:string):string{return graph.value?.nodes.find(n=>n.id===id)?.name??id;}
function masteryLabel(id:string):string{if(mastery.value?.graph_version!==graph.value?.graph_version)return '掌握度未知';const m=mastery.value?.items.find(m=>m.knowledge_node_id===id);return !m||m.status==='unseen'?'掌握度未知':`${({weak:'需要巩固',learning:'学习中',mastered:'已掌握'} as Record<string,string>)[m.status]} · ${Math.round(m.score*100)}%`;}
function persist():void{if(owner.value)writeStored(key(),{selected:selectedId.value,target:targetId.value,graph:requestedGraph.value,view:view.value,pending:pending.value});}
function select(id:string):void{selectedId.value=id;persist();}
function switchView(value:'graph'|'list'):void{view.value=value;persist();}
const layout=computed(()=>{
 const all=graph.value?.nodes??[];const depth=new Map<string,number>();const used=new Map<number,number>();
 function level(id:string,visiting=new Set<string>()):number{if(depth.has(id))return depth.get(id)!;if(visiting.has(id))return 0;const node=all.find(n=>n.id===id);const branch=new Set(visiting).add(id);const value=node?.prerequisites.length?1+Math.max(...node.prerequisites.map(p=>level(p,branch))):0;depth.set(id,value);return value;}
 const nodes=all.map(n=>{const d=level(n.id);const row=used.get(d)??0;used.set(d,row+1);return {...n,x:24+d*200,y:24+row*86};});
 const edges=nodes.flatMap(n=>n.prerequisites.flatMap(p=>{const from=nodes.find(n=>n.id===p);return from?[{id:`${p}:${n.id}`,x1:from.x+160,y1:from.y+26,x2:n.x,y2:n.y+26}]:[];}));
 return {nodes,edges,width:Math.max(500,...nodes.map(n=>n.x+184)),height:Math.max(180,...nodes.map(n=>n.y+76))};
});
async function initialize():Promise<void>{const epoch=++sequence;loading.value=true;error.value='';pathError.value='';evidenceError.value='';courseError.value='';
 try{const session=await ensureCatalogSession();if(!alive||epoch!==sequence)return;if(owner.value!==session.owner){graph.value=undefined;mastery.value=undefined;path.value=null;selectedId.value='';targetId.value='';pending.value=undefined;courseManifest.value=undefined;originalGoal.value='';}owner.value=session.owner;
 const saved=readStored<{selected:string;target:string;graph:string;view:string;pending?:Pending}>(key());
 requestedGraph.value=saved?.graph??'';selectedId.value=saved?.selected??'';targetId.value=saved?.target??'';pending.value=saved?.pending;
 const current=await loadGraph();if(!alive||epoch!==sequence)return;currentGraph.value=current.graph_version;if(!requestedGraph.value)requestedGraph.value=current.graph_version;
 const results=await Promise.allSettled([saved?.graph&&saved.graph!==current.graph_version?loadGraphVersion(saved.graph):Promise.resolve(current),loadMastery(),loadCatalog(),saved?.target?loadCurrentPath(saved.target):Promise.resolve(null),props.courseId?Promise.all([readCourse(props.courseId),readManifest(props.courseId,props.courseVersion)]):Promise.resolve(null)]);
 if(!alive||epoch!==sequence)return;const [structure,records,signed,stored,course]=results;
 if(structure.status==='rejected')throw new Error('原知识结构版本无法读取，请主动选择当前知识结构；不会静默替换。');graph.value=structure.value;
 if(records.status==='fulfilled')mastery.value=records.value;else{mastery.value=undefined;evidenceError.value='掌握度证据未读到，节点仍可浏览；不显示推测成绩。';}
 if(signed.status==='fulfilled')catalog.value=signed.value;else{catalog.value=undefined;evidenceError.value+=' 签核课程可用性尚未确认。';}
 targetId.value=saved?.target??'';selectedId.value=saved?.selected??current.nodes[0]?.id??'';view.value=saved?.view==='list'?'list':'graph';pending.value=saved?.pending;
 if(stored.status==='fulfilled')path.value=stored.value;else{path.value=null;pathError.value='原路径未能读取；不会重新规划。';}
 if(course.status==='fulfilled'&&course.value){originalGoal.value=course.value[0].original_goal;courseManifest.value=course.value[1];}else if(props.courseId){courseManifest.value=undefined;originalGoal.value='';courseError.value='无法读取当前课程关联。';}
 }catch(failure){if(alive&&epoch===sequence){error.value=failure instanceof Error?failure.message:'图谱未能读取。';graph.value=undefined;}}
 finally{if(alive&&epoch===sequence)loading.value=false;}}
async function latest():Promise<void>{if(busy.value||loading.value)return;loading.value=true;error.value='';try{const value=await loadGraph();if(!alive)return;graph.value=value;requestedGraph.value=value.graph_version;currentGraph.value=value.graph_version;if(!value.nodes.some(n=>n.id===selectedId.value))selectedId.value='';persist();}catch{if(alive)error.value='当前知识结构未能读取。';}finally{if(alive)loading.value=false;}}
async function showPathGraph():Promise<void>{if(!path.value||loading.value||busy.value)return;loading.value=true;try{const value=await loadGraphVersion(path.value.graph_version);if(alive){graph.value=value;requestedGraph.value=value.graph_version;persist();}}catch{if(alive)pathError.value='历史路径对应知识结构不可用，路径记录保留。';}finally{if(alive)loading.value=false;}}
async function plan(retry=false):Promise<void>{if(busy.value||loading.value||!owner.value)return;if(!retry&&(historical.value||!selected.value||pending.value))return;busy.value=true;pathError.value='';
 try{const session=await ensureCatalogSession();if(!alive)return;if(session.owner!==owner.value)throw new Error('学习身份已变化，请重新读取。');if(!retry)pending.value={kind:path.value?.target_node_id===selectedId.value?'replan':'plan',target:selectedId.value,key:crypto.randomUUID(),expected:path.value?.version};const request=pending.value;if(!request)return;targetId.value=request.target;persist();const value=request.kind==='replan'?await replanPath({targetNodeId:request.target,expectedVersion:request.expected!,csrfToken:session.csrf,idempotencyKey:request.key,reason:'learner_request'}):await planPath(request.target,session.csrf,request.key);if(!alive)return;path.value=value;targetId.value=value.target_node_id;pending.value=undefined;persist();}
 catch(failure){if(alive){if(failure instanceof PathRequestError&&failure.code==='PATH_VERSION_CONFLICT'){pending.value=undefined;persist();}pathError.value=failure instanceof Error?failure.message:'规划结果未确认，请确认原请求。';}}finally{if(alive)busy.value=false;}}
onMounted(initialize);onBeforeUnmount(()=>{alive=false;sequence+=1;persist();});
</script>
<template>
  <main class="page-view graph-paths">
    <p class="page-eyebrow">
      关系帮助理解，建议保留选择
    </p><h1>图谱与路径</h1><p class="page-lead">
      节点不等于课程，先修建议不会替你改写学习目标。查看与刷新不会生成课程。
    </p>
    <div class="action-row">
      <button
        class="secondary"
        type="button"
        :disabled="loading || busy"
        @click="initialize"
      >
        重新读取记录
      </button><button
        v-if="historical || error"
        class="secondary"
        type="button"
        :disabled="loading || busy"
        @click="latest"
      >
        明确查看当前知识结构
      </button>
    </div>
    <WorkspaceState
      v-if="loading"
      kind="loading"
      detail="正在读取知识结构与已有记录。"
    />
    <WorkspaceState
      v-if="error"
      kind="error"
      :detail="error"
    />
    <p
      v-if="evidenceError"
      role="status"
    >
      {{ evidenceError }}
    </p>
    <section
      v-if="courseId"
      class="surface course-associations"
      aria-label="实际课程关联"
    >
      <h2>当前课程与关联</h2><p v-if="courseError">
        {{ courseError }}
      </p><template v-else>
        <p>原始目标：{{ originalGoal }}</p><p>实际读取课程 v{{ courseVersion }}；图谱推荐不改变其目标或教学内容。</p><ul v-if="courseManifest?.node_links.length">
          <li
            v-for="(link,index) in courseManifest.node_links"
            :key="index"
          >
            {{ link.node_id }} · {{ link.graph_version }} · {{ link.relation }} · {{ link.scene_id ? `场景 ${link.scene_id}` : '课程级关联' }} · 来源 {{ link.source }}
          </li>
        </ul><p v-else>
          没有可靠节点关联；仍可学习和保留课程内表现，不虚构掌握度。
        </p>
      </template>
    </section>
    <template v-if="graph">
      <div class="action-row">
        <span class="status-pill">知识结构 {{ graph.graph_version }} · {{ graph.nodes.length }} 个节点</span><span
          v-if="historical"
          class="status-warning"
        >历史结构 · 不自动重规划</span><button
          type="button"
          class="secondary"
          :aria-pressed="view==='graph'"
          @click="switchView('graph')"
        >
          关系图
        </button><button
          type="button"
          class="secondary"
          :aria-pressed="view==='list'"
          @click="switchView('list')"
        >
          节点列表
        </button>
      </div>
      <div class="graph-layout">
        <div class="surface graph-browse">
          <template v-if="view==='graph'">
            <p>箭头由前置知识指向后续节点。可横向滚动；也可切换列表逐项浏览。</p><div
              class="graph-scroll"
              tabindex="0"
              aria-label="知识关系图，可滚动"
            >
              <svg
                :width="layout.width"
                :height="layout.height"
                role="group"
                aria-label="知识节点与先修关系"
              ><defs><marker
                id="prerequisite-arrow"
                markerWidth="8"
                markerHeight="8"
                refX="7"
                refY="4"
                orient="auto"
              ><path
                d="M0,0 L8,4 L0,8"
                fill="currentColor"
              /></marker></defs><line
                v-for="edge in layout.edges"
                :key="edge.id"
                v-bind="{x1:edge.x1,y1:edge.y1,x2:edge.x2,y2:edge.y2}"
                marker-end="url(#prerequisite-arrow)"
              /><g
                v-for="node in layout.nodes"
                :key="node.id"
                :transform="`translate(${node.x},${node.y})`"
                role="button"
                tabindex="0"
                :aria-label="node.name"
                :aria-pressed="selectedId===node.id"
                @click="select(node.id)"
                @keydown.enter.prevent="select(node.id)"
                @keydown.space.prevent="select(node.id)"
              ><rect
                width="160"
                height="56"
                rx="8"
              /><text
                x="12"
                y="23"
              >{{ node.name.length>12?`${node.name.slice(0,11)}…`:node.name }}</text><text
                x="12"
                y="43"
                class="graph-node-state"
              >{{ masteryLabel(node.id) }}</text></g></svg>
            </div>
          </template>
          <ul
            v-else
            class="graph-node-list"
            aria-label="全部知识点"
          >
            <li
              v-for="node in graph.nodes"
              :key="node.id"
            >
              <button
                type="button"
                :aria-pressed="selectedId===node.id"
                @click="select(node.id)"
              >
                <strong>{{ node.name }}</strong><span>{{ masteryLabel(node.id) }}</span>
              </button>
            </li>
          </ul>
          <p v-if="!graph.nodes.length">
            此版本没有可浏览节点。
          </p>
        </div>
        <section
          class="surface graph-detail"
          aria-label="节点详情"
        >
          <template v-if="selected">
            <h2>{{ selected.name }}</h2><p>{{ masteryLabel(selected.id) }}</p><h3>先修关联</h3><div class="action-row">
              <button
                v-for="id in selected.prerequisites"
                :key="id"
                class="secondary"
                type="button"
                @click="select(id)"
              >
                {{ name(id) }}
              </button>
            </div><p v-if="!selected.prerequisites.length">
              没有列出的前置节点。
            </p><p v-if="!catalog || catalog.status!=='ready'">
              签核课程可用性尚未确认。
            </p><template v-else-if="signed">
              <p>已有签核课程 · {{ signed.version }}</p><button
                class="secondary"
                type="button"
                @click="emit('catalog')"
              >
                查看签核课程目录
              </button>
            </template><p v-else>
              节点存在，尚无对应签核课程。
            </p><button
              class="primary"
              type="button"
              @click="emit('goal',`我想理解${selected.name}`)"
            >
              带入学习目标
            </button><p>先回到学习页确认输入；不会自动生成，也不强制从先修节点开始。</p><button
              class="secondary"
              type="button"
              :disabled="loading || busy || historical || Boolean(pending)"
              @click="plan(false)"
            >
              明确规划该节点路径
            </button>
          </template><p v-else>
            请选择节点。原选择在此版本不存在时，不自动替换。
          </p>
        </section>
      </div>
    </template>
    <section
      class="surface graph-recommendation"
      aria-label="已保存路径"
    >
      <h2>目标与下一步建议</h2><p
        v-if="pathError"
        role="alert"
      >
        {{ pathError }}
      </p><button
        v-if="pending"
        class="secondary"
        type="button"
        :disabled="busy || loading"
        @click="plan(true)"
      >
        确认原路径请求
      </button><p v-if="!path">
        {{ targetId ? '原目标路径尚未读到。' : '尚无已保存的节点目标路径。可直接按自己的目标学习。' }}
      </p><template v-else>
        <p>路径目标：{{ name(path.target_node_id) }} · 路径 v{{ path.version }} · {{ path.graph_version }}</p><p>推荐当前：{{ path.current_node_id ? name(path.current_node_id) : '路径已完成' }}；下一步：{{ path.next_node_id ? name(path.next_node_id) : '无后续节点' }}</p><p v-if="path.is_stale">
          推荐依据已有变化，保留原记录；仅在明确规划时更新。
        </p><ol>
          <li
            v-for="id in path.nodes"
            :key="id"
          >
            {{ name(id) }}
          </li>
        </ol><h3>推荐依据</h3><ul>
          <li
            v-for="(reason,index) in path.reasons"
            :key="index"
          >
            {{ reason.summary }}
          </li>
        </ul><button
          v-if="path.graph_version!==graph?.graph_version"
          class="secondary"
          type="button"
          @click="showPathGraph"
        >
          读取路径对应历史结构
        </button><p>路径建议、当前选择与实际课程关联分别保留，不自动替换。</p>
      </template>
    </section>
  </main>
</template>
