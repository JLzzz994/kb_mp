<script setup lang="ts">
import { computed, ref } from "vue";
import { AlertCircle, CheckCircle2, FileUp, LoaderCircle, Trash2 } from "lucide-vue-next";

import { ApiError } from "@/api/client";
import { importFiles, type ImportTaskResponse } from "@/api/knowledge";
import PageHeader from "@/components/shared/PageHeader.vue";
import { formatBytes } from "@/lib/utils";

const allowedExt = ["pdf", "md", "docx", "txt"];
const singleLimit = 20 * 1024 * 1024;
const batchLimit = 200 * 1024 * 1024;

interface PickedFile {
  file: File;
  error?: string;
}

const fileInput = ref<HTMLInputElement | null>(null);
const picked = ref<PickedFile[]>([]);
const dragging = ref(false);
const uploading = ref(false);
const result = ref<ImportTaskResponse | null>(null);
const error = ref<string | null>(null);

const validFiles = computed(() => picked.value.filter((item) => !item.error).map((item) => item.file));
const hasInvalid = computed(() => picked.value.some((item) => item.error));
const totalSize = computed(() => picked.value.reduce((sum, item) => sum + item.file.size, 0));

function extOf(name: string): string {
  return name.split(".").pop()?.toLowerCase() ?? "";
}

function validate(file: File): PickedFile {
  const ext = extOf(file.name);
  if (!allowedExt.includes(ext)) {
    return { file, error: `不支持的格式 .${ext}（仅 PDF / MD / DOCX / TXT）` };
  }
  if (file.size > singleLimit) {
    return { file, error: `超过单文件 20MB 限制（${formatBytes(file.size)}）` };
  }
  return { file };
}

function addFiles(files: File[]) {
  result.value = null;
  error.value = null;
  const incoming = files.map(validate);
  const next = [...picked.value, ...incoming];
  const bytes = next.reduce((sum, item) => sum + item.file.size, 0);
  if (bytes > batchLimit) {
    error.value = `批量总大小超过 200MB（当前 ${formatBytes(bytes)}），请分批上传`;
    return;
  }
  picked.value = next;
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  addFiles(Array.from(input.files ?? []));
  input.value = "";
}

function onDrop(event: DragEvent) {
  dragging.value = false;
  addFiles(Array.from(event.dataTransfer?.files ?? []));
}

async function upload() {
  if (!validFiles.value.length || hasInvalid.value) return;
  uploading.value = true;
  error.value = null;
  result.value = null;
  try {
    result.value = await importFiles(validFiles.value);
    picked.value = [];
  } catch (err) {
    if (err instanceof ApiError) {
      const reasonMap: Record<string, string> = {
        content_duplicate: "存在重复内容（SHA-256 哈希命中），请检查文件",
        file_too_large: "文件超过大小限制",
        unsupported_media_type: "存在不支持的文件格式",
      };
      error.value = reasonMap[err.errorCode ?? ""] ?? err.message;
    } else {
      error.value = "上传失败，请重试";
    }
  } finally {
    uploading.value = false;
  }
}
</script>

<template>
  <div class="animate-fade-up">
    <PageHeader
      title="产品文档导入"
      description="PDF/DOCX 优先走 MinerU 结构化解析；失败时按配置回退原生解析器，再按章节/页码切片并写入 Milvus。"
    >
      <template #actions>
        <button
          class="flex h-10 items-center gap-2 rounded-md bg-brand px-4 text-sm font-bold text-navy-deep disabled:opacity-50"
          :disabled="uploading || validFiles.length === 0 || hasInvalid"
          @click="upload"
        >
          <LoaderCircle v-if="uploading" class="h-4 w-4 animate-spin" aria-hidden="true" />
          <FileUp v-else class="h-4 w-4" aria-hidden="true" />
          {{ uploading ? "上传中…" : `开始导入（${validFiles.length}）` }}
        </button>
      </template>
    </PageHeader>

    <section
      class="rounded-xl border-2 border-dashed bg-card p-8 text-center transition"
      :class="dragging ? 'border-brand bg-brand-soft/50' : 'border-boundary'"
      @dragenter.prevent="dragging = true"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <FileUp class="mx-auto h-10 w-10 text-brand" aria-hidden="true" />
      <p class="mt-3 font-display font-bold text-ink">拖拽产品文档到此处</p>
      <p class="mt-1 text-sm text-secondarytext">支持 PDF / DOCX / Markdown / TXT；单文件 ≤ 20MB，批次 ≤ 200MB</p>
      <button
        class="mt-4 rounded-md border border-boundary bg-white px-4 py-2 text-sm font-medium text-ink hover:bg-mist"
        @click="fileInput?.click()"
      >
        选择文件
      </button>
      <input
        ref="fileInput"
        type="file"
        multiple
        accept=".pdf,.docx,.md,.txt"
        class="hidden"
        @change="onFileChange"
      />
    </section>

    <div v-if="error" class="mt-4 flex items-center gap-2 rounded-lg border border-danger/30 bg-danger-soft p-4 text-sm text-danger">
      <AlertCircle class="h-4 w-4" aria-hidden="true" />{{ error }}
    </div>

    <section v-if="picked.length" class="mt-5 overflow-hidden rounded-xl border border-boundary bg-card">
      <header class="flex items-center justify-between border-b border-boundary px-5 py-3">
        <p class="font-display font-bold text-ink">待导入文件</p>
        <span class="code-text text-secondarytext">{{ picked.length }} 个 · {{ formatBytes(totalSize) }}</span>
      </header>
      <ul class="divide-y divide-boundary">
        <li v-for="(item, index) in picked" :key="`${item.file.name}-${index}`" class="flex items-center gap-3 px-5 py-3">
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm font-medium text-ink">{{ item.file.name }}</p>
            <p class="code-text mt-0.5 text-secondarytext">{{ formatBytes(item.file.size) }}</p>
            <p v-if="item.error" class="mt-1 text-xs text-danger">{{ item.error }}</p>
          </div>
          <button class="rounded-md p-2 text-secondarytext hover:bg-danger-soft hover:text-danger" @click="picked.splice(index, 1)">
            <Trash2 class="h-4 w-4" aria-hidden="true" />
          </button>
        </li>
      </ul>
    </section>

    <section v-if="result" class="mt-5 rounded-xl border border-brand/40 bg-brand-soft p-5">
      <p class="flex items-center gap-2 font-display font-bold text-ink">
        <CheckCircle2 class="h-5 w-5 text-brand" aria-hidden="true" />
        导入任务已创建
      </p>
      <p class="code-text mt-2 text-secondarytext">task_id: {{ result.task_id }}</p>
      <p class="mt-2 text-sm text-primarytext">
        接受 {{ result.accepted_count ?? result.accepted ?? 0 }} 个文件，
        拒绝 {{ result.rejected.length }} 个文件。
      </p>
      <ul v-if="result.rejected.length" class="mt-3 space-y-1 text-xs text-danger">
        <li v-for="item in result.rejected" :key="item.filename">{{ item.filename }}：{{ item.reason }}</li>
      </ul>
    </section>
  </div>
</template>
