<script setup lang="ts">
import { computed } from 'vue';
const props=defineProps<{modelValue:unknown;label:string}>();
const emit=defineEmits<{'update:modelValue':[value:unknown]}>();
const labels:Record<string,string>={description:'补充描述',current_topic:'当前学习目标',current_difficulty:'当前困难',major:'专业方向',education_level:'教育阶段',code_first:'先看代码',topic:'相关主题',level:'自述阶段',preferred_language:'偏好语言'};
const entries=computed(()=>props.modelValue&&typeof props.modelValue==='object'&&!Array.isArray(props.modelValue)?Object.entries(props.modelValue):[]);
function update(key:string,value:unknown):void{emit('update:modelValue',Object.fromEntries(entries.value.map(([k,v])=>[k,k===key?value:v])));}
function remove(key:string):void{emit('update:modelValue',Object.fromEntries(entries.value.filter(([k])=>k!==key)));}
function at(index:number,value:unknown):void{if(Array.isArray(props.modelValue))emit('update:modelValue',props.modelValue.map((v:unknown,i:number)=>i===index?value:v));}
</script>
<template>
  <fieldset
    v-if="Array.isArray(modelValue)"
    class="profile-value-editor"
  >
    <legend>{{ label }}</legend><div
      v-for="(value,index) in modelValue"
      :key="index"
    >
      <ProfileValueEditor
        :model-value="value"
        :label="`${label} ${index+1}`"
        @update:model-value="at(index,$event)"
      /><button
        class="secondary"
        type="button"
        @click="emit('update:modelValue',modelValue.filter((_:unknown,i:number)=>i!==index))"
      >
        移除第 {{ index+1 }} 条
      </button>
    </div><button
      class="secondary"
      type="button"
      @click="emit('update:modelValue',[...modelValue,''])"
    >
      添加一条描述
    </button>
  </fieldset>
  <fieldset
    v-else-if="modelValue && typeof modelValue==='object'"
    class="profile-value-editor"
  >
    <legend>{{ label }}</legend><div
      v-for="[key,value] in entries"
      :key="key"
    >
      <ProfileValueEditor
        :model-value="value"
        :label="labels[key]??key"
        @update:model-value="update(key,$event)"
      /><button
        class="secondary"
        type="button"
        @click="remove(key)"
      >
        移除 {{ labels[key]??key }}
      </button>
    </div><button
      v-if="!entries.some(([key])=>key==='description')"
      class="secondary"
      type="button"
      @click="emit('update:modelValue',Object.fromEntries([...entries,['description','']]))"
    >
      补充一段自述
    </button>
  </fieldset>
  <label
    v-else-if="typeof modelValue==='boolean'"
    class="profile-value-editor"
  ><input
    type="checkbox"
    :checked="modelValue"
    @change="emit('update:modelValue',($event.target as HTMLInputElement).checked)"
  >{{ label }}</label>
  <label
    v-else
    class="profile-value-editor"
  >{{ label }}<input
    v-if="typeof modelValue==='number'"
    type="number"
    :value="modelValue"
    @input="Number.isFinite(($event.target as HTMLInputElement).valueAsNumber)&&emit('update:modelValue',($event.target as HTMLInputElement).valueAsNumber)"
  ><textarea
    v-else
    rows="2"
    maxlength="4000"
    :value="String(modelValue??'')"
    @input="emit('update:modelValue',($event.target as HTMLTextAreaElement).value)"
  /></label>
</template>
