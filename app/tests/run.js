// app/tests/run.js — node 로 도는 최소 러너 (의존성 없음)
//
// 각 *.test.js 파일은 자기 완결형이다: 스스로 단언하고 스스로
// process.exit() 한다(overview.test.js 가 먼저 그렇게 만들어 뒀다). 그래서
// 한 파일 안에서 import 로 묶으면 첫 파일의 process.exit 이 나머지를 끊는다
// — 그러니 파일마다 자식 프로세스로 따로 돌리고 종료 코드만 모은다.
// 새 테스트 파일은 이 디렉터리에 *.test.js 로 두기만 하면 자동으로 걸린다
// — run.js 를 따로 고칠 일이 없다.
import { readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { spawnSync } from "node:child_process";

const dir = path.dirname(fileURLToPath(import.meta.url));
const files = readdirSync(dir).filter((f) => f.endsWith(".test.js")).sort();

let failed = 0;
for (const file of files) {
  console.log(`--- ${file} ---`);
  const result = spawnSync(process.execPath, [path.join(dir, file)], { stdio: "inherit" });
  if (result.status !== 0) failed++;
}
process.exit(failed ? 1 : 0);
