// app/tests/run.js — node 로 도는 최소 러너 (의존성 없음)
//
// 각 *.test.js 파일은 자기 완결형이다: 스스로 단언하고 스스로
// process.exit() 한다(overview.test.js 가 먼저 그렇게 만들어 뒀다). 그래서
// 한 파일 안에서 import 로 묶으면 첫 파일의 process.exit 이 나머지를 끊는다
// — 그러니 파일마다 자식 프로세스로 따로 돌리고 종료 코드만 모은다.
// 새 테스트 파일은 이 디렉터리에 *.test.js 로 두기만 하면 자동으로 걸린다
// — run.js 를 따로 고칠 일이 없다.
//
// R42 — 이후 모든 태스크의 완료 게이트가 "node app/tests/run.js" 하나다.
// 발견된 *.test.js 가 0개인데 조용히 종료코드 0으로 끝나면, 테스트 폴더가
// 옮겨지거나 필터에 오타가 나도 게이트가 초록불을 켠다 — 뒤따르는 태스크
// 전부가 그 거짓 초록을 믿고 오염된다. 그래서 0개 발견은 실패로 취급한다.
// 첫 인자로 스캔 디렉터리를 받을 수 있게 해 뒀다 — 이 가드 자체를
// run-guard.test.js 가 빈 임시 디렉터리를 가리켜 검증한다.
import { readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { spawnSync } from "node:child_process";

const dir = process.argv[2] ? path.resolve(process.argv[2]) : path.dirname(fileURLToPath(import.meta.url));
const files = readdirSync(dir).filter((f) => f.endsWith(".test.js")).sort();

if (files.length === 0) {
  console.error(`FAIL 러너 가드: ${dir} 에서 *.test.js 를 하나도 못 찾았다 — 테스트 스위트가 아무것도 안 돌면서 조용히 통과한 것처럼 보이는 사고를 막는다(R42)`);
  process.exit(1);
}

let failed = 0;
for (const file of files) {
  console.log(`--- ${file} ---`);
  const result = spawnSync(process.execPath, [path.join(dir, file)], { stdio: "inherit" });
  if (result.status !== 0) failed++;
}
process.exit(failed ? 1 : 0);
