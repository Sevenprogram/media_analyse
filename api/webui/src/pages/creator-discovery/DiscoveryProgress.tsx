import React from "react";
import { Check, Loader2, XCircle } from "lucide-react";
import { Button } from "../../components/ui";
import { DISCOVERY_STAGES, DiscoveryStageKey, progressStageKey } from "./utils";

type Props = {
  active: boolean;
  stage?: string;
  status: string;
  percent: number;
  totalFound?: number;
  elapsedSeconds?: number;
  onCancel?: () => void;
  canceling?: boolean;
};

const STATUS_DONE = ["completed", "complete"];
const STATUS_FAIL = ["failed", "cancelled"];

function formatElapsed(seconds: number | undefined) {
  if (!seconds || !Number.isFinite(seconds) || seconds < 0) return "00:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function stageOrder(stage: DiscoveryStageKey) {
  return DISCOVERY_STAGES.findIndex((item) => item.key === stage);
}

export function DiscoveryProgress({ active, stage, status, percent, totalFound, elapsedSeconds, onCancel, canceling }: Props) {
  const currentStage = progressStageKey(stage);
  const currentIndex = stageOrder(currentStage);
  const isDone = STATUS_DONE.includes(status);
  const isFail = STATUS_FAIL.includes(status);
  const running = active && !isDone && !isFail;

  return (
    <div className={`cd-progress ${isDone ? "is-done" : ""} ${isFail ? "is-fail" : ""}`}>
      <div className="cd-progress-track" aria-hidden>
        <i style={{ width: `${Math.min(100, Math.max(4, percent))}%` }} />
      </div>

      <div className="cd-progress-body">
        <div className="cd-progress-label">
          <strong>发现进度</strong>
          {running && <Loader2 size={14} className="spin" />}
        </div>

        <ol className="cd-stepper">
          {DISCOVERY_STAGES.map((step, index) => {
            const done = isDone || index < currentIndex;
            const isCurrent = !isDone && index === currentIndex;
            return (
              <li
                key={step.key}
                className={`cd-step ${done ? "is-done" : ""} ${isCurrent ? "is-current" : ""}`}
              >
                <span className="cd-step-marker">
                  {done ? <Check size={12} /> : <span className="cd-step-index">{index + 1}</span>}
                </span>
                <span className="cd-step-label">{step.label}</span>
                {index < DISCOVERY_STAGES.length - 1 && <span className="cd-step-bar" aria-hidden />}
              </li>
            );
          })}
        </ol>

        <div className="cd-progress-meta">
          {isDone ? (
            <span>
              已发现 <strong>{totalFound ?? 0}</strong> 位达人，用时 <strong>{formatElapsed(elapsedSeconds)}</strong>
            </span>
          ) : running ? (
            <span>
              已发现 <strong>{totalFound ?? 0}</strong> 位达人，用时 <strong>{formatElapsed(elapsedSeconds)}</strong>
            </span>
          ) : isFail ? (
            <span className="cd-progress-fail">任务已 {status === "cancelled" ? "取消" : "失败"}</span>
          ) : (
            <span>等待启动智能发现</span>
          )}
          {running && onCancel && (
            <Button type="button" size="sm" variant="ghost" onClick={onCancel} disabled={canceling}>
              {canceling ? <Loader2 size={14} className="spin" /> : <XCircle size={14} />}
              取消
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
