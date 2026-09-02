// app/tests/run-guard.test.js — run.js 의 "발견 0개 → 실패" 가드(R42)를 검증한다.
// 이 가드가 없으면 테스트 폴더가 옮겨지거나 필터에 오타가 나도 run.js 가
// 아무것도 안 돌리고 조용히 종료코드 0으로 끝난다 — 이후 모든 태스크의
// 완료 게이트가 "node app/tests/run.js" 하나이므로, 그 게이트가 거짓말을
// 하면 뒤따르는 태스크 전부가 오염된다. run.js 가 첫 인자로 스캔 디렉터리를
// 받게 해 뒀으므로, 여기서는 빈 임시 디렉터리를 가리켜 실패하는지만 본다.
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const runJs = path.join(path.dirname(fileURLToPath(import.meta.url)), "run.js");

let failed = 0;
const eq = (got, want, label) => {
  if (got !== want) { failed++; console.error(`FAIL ${label}: ${got} !== ${want}`); }
  else console.log(`ok ${label}`);
};

const emptyDir = mkdtempSync(path.join(tmpdir(), "run-guard-"));
try {
  const result = spawnSync(process.execPath, [runJs, emptyDir], { encoding: "utf8" });
  eq(result.status === 0, false, "발견된 *.test.js 가 0개면 종료코드 0 이 아니다");
  eq(result.stderr.includes("하나도 못 찾았다"), true, "왜 실패했는지 메시지를 남긴다");
} finally {
  rmSync(emptyDir, { recursive: true, force: true });
}

process.exit(failed ? 1 : 0);
