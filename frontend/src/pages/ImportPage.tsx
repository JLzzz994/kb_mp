import { useRef, useState } from "react";
import { FileUp, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { importFiles, type ImportTaskResponse } from "@/api/knowledge";
import { ApiError } from "@/api/client";
import { formatBytes, cn } from "@/lib/utils";

const ALLOWED_EXT = ["pdf", "md", "docx", "txt"];
const SINGLE_LIMIT = 20 * 1024 * 1024; // 单文件 20MB
const BATCH_LIMIT = 200 * 1024 * 1024; // 批量 200MB

interface PickedFile {
  file: File;
  error?: string; // 客户端预校验（类型/大小）
}

function extOf(name: string): string {
  return name.split(".").pop()?.toLowerCase() ?? "";
}

export default function ImportPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<PickedFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<ImportTaskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const validate = (incoming: File[]): PickedFile[] => {
    return incoming.map((file) => {
      const ext = extOf(file.name);
      if (!ALLOWED_EXT.includes(ext)) {
        return { file, error: `不支持的格式 .${ext}（仅 PDF / MD / DOCX / TXT）` };
      }
      if (file.size > SINGLE_LIMIT) {
        return { file, error: `超过单文件 20MB 限制（${formatBytes(file.size)}）` };
      }
      return { file };
    });
  };

  const addFiles = (incoming: File[]) => {
    setResult(null);
    setError(null);
    setFiles((prev) => {
      const merged = [...prev, ...validate(incoming)];
      // 客户端提前拦截批量总大小 200MB
      const total = merged.reduce((s, f) => s + f.file.size, 0);
      if (total > BATCH_LIMIT) {
        setError(`批量总大小超过 200MB（当前 ${formatBytes(total)}），请分批上传`);
        return prev;
      }
      return merged;
    });
  };

  const validFiles = files.filter((f) => !f.error).map((f) => f.file);
  const hasInvalid = files.some((f) => f.error);

  const handleUpload = async () => {
    if (validFiles.length === 0) return;
    setUploading(true);
    setError(null);
    setResult(null);
    try {
      const resp = await importFiles(validFiles);
      setResult(resp);
      setFiles([]);
    } catch (err) {
      // 409 content_duplicate / 413 file_too_large / 415 unsupported_media_type
      if (err instanceof ApiError) {
        const reasonMap: Record<string, string> = {
          content_duplicate: "存在重复内容（SHA-256 哈希命中），请检查文件",
          file_too_large: "文件超过大小限制",
          unsupported_media_type: "存在不支持的文件格式",
        };
        setError(`${reasonMap[err.errorCode ?? ""] ?? err.message}`);
      } else {
        setError("上传失败，请重试");
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="animate-fade-up">
      <PageHeader
        title="知识导入中心"
        description="上传 PDF / Markdown / DOCX / TXT 文档，服务端解析切片后向量化入库。"
        actions={
          <Button onClick={() => void handleUpload()} disabled={uploading || validFiles.length === 0 || hasInvalid}>
            {uploading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> 上传中…
              </>
            ) : (
              <>
                <FileUp className="h-4 w-4" aria-hidden /> 上传 {validFiles.length > 0 ? `（${validFiles.length} 个文件）` : ""}
              </>
            )}
          </Button>
        }
      />

      {/* 拖拽区 */}
      <div
        role="button"
        tabIndex={0}
        aria-label="拖拽或选择文件上传"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(Array.from(e.dataTransfer.files));
        }}
        className={cn(
          "flex min-h-[200px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition",
          dragging ? "border-brand bg-brand-soft" : "border-boundary bg-card/60 hover:border-brand/60",
        )}
      >
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-mist">
          <FileUp className="h-6 w-6 text-brand" aria-hidden />
        </div>
        <p className="mt-4 font-display text-base font-bold text-ink">拖拽文件到此处，或点击选择</p>
        <p className="mt-1.5 text-sm text-secondarytext">
          支持 PDF / MD / DOCX / TXT · 单文件 ≤ 20MB · 批量 ≤ 200MB
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.md,.docx,.txt"
          className="hidden"
          onChange={(e) => {
            addFiles(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />
      </div>

      {error && (
        <p role="alert" className="mt-4 flex items-center gap-2 rounded-md bg-danger-soft px-4 py-3 text-sm text-danger">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden /> {error}
        </p>
      )}

      {/* 待上传文件列表：文件级状态 */}
      {files.length > 0 && (
        <ul className="mt-4 divide-y divide-boundary rounded-lg border border-boundary bg-card">
          {files.map((f, i) => (
            <li key={`${f.file.name}-${i}`} className="flex items-center gap-3 px-4 py-3">
              {f.error ? (
                <AlertCircle className="h-4 w-4 shrink-0 text-danger" aria-hidden />
              ) : (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-brand" aria-hidden />
              )}
              <span className="code-text min-w-0 flex-1 truncate text-[13px] text-primarytext">
                {f.file.name}
              </span>
              <span className="shrink-0 text-xs text-secondarytext">{formatBytes(f.file.size)}</span>
              {f.error && <span className="shrink-0 text-xs text-danger">{f.error}</span>}
              <button
                aria-label={`移除 ${f.file.name}`}
                onClick={() => setFiles((prev) => prev.filter((_, idx) => idx !== i))}
                className="h-11 shrink-0 px-2 text-sm text-secondarytext hover:text-danger"
              >
                移除
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* 导入结果 */}
      {result && (
        <div className="mt-4 rounded-lg border border-brand/40 bg-brand-soft px-4 py-4">
          <p className="flex items-center gap-2 font-medium text-ink">
            <CheckCircle2 className="h-4 w-4 text-brand" aria-hidden />
            已受理 {result.accepted_count ?? result.accepted ?? validFiles.length} 个文件（任务 {result.task_id}），解析与向量化进行中
          </p>
          {result.rejected?.length > 0 && (
            <ul className="mt-2 space-y-1">
              {result.rejected.map((r) => (
                <li key={r.filename} className="text-[13px] text-secondarytext">
                  {r.filename}：{r.reason}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-xs text-secondarytext">
            可前往「知识单元」查看解析与向量化状态（active / vector_pending / failed）。
          </p>
        </div>
      )}
    </div>
  );
}
