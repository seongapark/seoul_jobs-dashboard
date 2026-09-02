# 수도권 구인구직 모바일 대시보드

서울고용센터에 제공하는 수도권 지역의 구인구직 현황 모바일 대시보드입니다.

## 문서와 계획

대시보드 명세와 개발 계획은 `docs/superpowers/` 디렉토리에 있습니다.

## 테스트 실행

```bash
python -m pytest -v      # 파이썬 파이프라인
node app/tests/run.js    # 화면(ES 모듈)
```

`.github/workflows/test.yml` 이 push·PR 마다 이 둘을 그대로 돌립니다.

## 데이터 수집

GitHub Actions 워크플로 둘이 `data/*.json` 을 자동으로 채우고 커밋합니다
(진입점: `pipeline/cli.py`).

| 워크플로 | 주기 | 받는 것 |
| --- | --- | --- |
| `.github/workflows/collect-monthly.yml` | 매월 5일 10:00 KST | EIS 유효구인구직·취업건수·피보험자·경력직이동(시군구/시도)과 24개월 시계열 |
| `.github/workflows/collect-halfyear.yml` | 6월 20일·12월 20일 10:00 KST | KOSIS 직종별사업체노동력조사(반기) — 직종별 표(`est.json`)와 산업별 표(`est_industry.json`) 둘 |

둘 다 `workflow_dispatch` 로 수동 실행할 수 있습니다. **검사가 실패하면
워크플로가 0이 아닌 코드로 죽어 커밋 단계가 돌지 않습니다** — 틀린 값이
`data/`에 들어가는 대신 워크플로가 실패로 표시됩니다.

`collect-halfyear.yml` 은 KOSIS OpenAPI 키가 필요합니다. 저장소 Settings →
Secrets and variables → Actions 에 `KOSIS_API_KEY` 를 등록해야 합니다(코드에는
넣지 않습니다).

## 배포

`main` 에 커밋이 올라가면(수집 워크플로의 자동 커밋 포함)
`.github/workflows/pages.yml` 이 GitHub Pages 로 배포합니다. 저장소 구조를
그대로 옮겨(`_site/app/`, `_site/data/`) `app/js/data.js` 의 기본 데이터
경로(`../data`)가 로컬·배포본 양쪽에서 똑같이 맞도록 합니다. 배포 주소는
저장소 Settings → Pages 에서 확인할 수 있습니다(형식:
`https://<조직 또는 계정>.github.io/<저장소>/app/`).
